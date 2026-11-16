"""显式运行一次 DeepSeek 和 D 校验，写出仓库外的内部验收证据。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict
from os import getenv
from pathlib import Path
from typing import Literal

from flowstudio_contracts import PlanningConfig, PlanningMode, SpecRevision, StrictModel, content_hash, sha256_hex
from flowstudio_contracts.constants import MAX_BODY_BYTES

from .planner import GraphCheck, ProposalKind, generate_validated_proposal
from .prompt import build_prompt
from .providers.deepseek import DeepSeekProvider, _contains_credential
from .types import Message, ModelLimits, ProviderFailure, ProviderResponse


class _InputError(ValueError):
    """用户可见的错误仅使用工具固定文本。"""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse 原始诊断可能包含调用方误输入的凭据。
        raise _InputError("命令行参数无效，请使用 --help")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _ArgumentParser(
        prog="python -m flowstudio_pm.real_validation",
        description="单次真实模型技术验收。结果始终等待人工复核。",
        allow_abbrev=False,
    )
    parser.add_argument("--enable-real", action="store_true", help="显式允许发起真实 DeepSeek 请求")
    parser.add_argument("--spec", type=Path, help="SpecRevision JSON 文件")
    parser.add_argument("--config", type=Path, help="PlanningConfig JSON 文件")
    parser.add_argument("--context-tokens", type=int, help="调用者确认的模型上下文限额")
    parser.add_argument("--max-output-tokens", type=int, help="调用者确认的模型输出限额")
    parser.add_argument("--api-key-env", help="凭据环境变量名")
    parser.add_argument("--evidence", type=Path, help="仓库外的新证据文件，父目录须已存在")
    return parser.parse_args(argv)


def _read_input(path: Path) -> bytes:
    if not path.is_file():
        raise _InputError("输入必须为可读的 JSON 文件")
    with path.open("rb") as source:
        data = source.read(MAX_BODY_BYTES + 1)
    if len(data) > MAX_BODY_BYTES:
        raise _InputError("输入 JSON 文件超过大小上限")
    return data


def _external_evidence_path(path: Path) -> Path:
    """以解析后的父目录检查 Git 标记，兼容 checkout 和 worktree。"""
    name = path.name
    if not name or name.casefold() == ".git" or path.is_symlink():
        raise _InputError("证据必须写入仓库外的新文件")
    if os.name == "nt" and (
        path.is_reserved() or name.endswith((".", " ")) or any(char in name for char in ':*?"<>|')
    ):
        raise _InputError("证据文件名无效")
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir():
        raise _InputError("证据文件的父级必须是已存在的目录")
    for directory in (parent, *parent.parents):
        try:
            (directory / ".git").lstat()
        except FileNotFoundError:
            continue
        raise _InputError("证据目录位于 Git checkout 或 worktree 内")
    target = parent / name
    try:
        target.lstat()
    except FileNotFoundError:
        return target
    raise _InputError("证据文件已存在")


class _RecordingProvider:
    """跟随 Task 1 发起的请求记录正文，普通规划入口仍不写盘。"""

    mode = PlanningMode.REAL
    fixture_id = None

    def __init__(self, provider: DeepSeekProvider) -> None:
        self._provider = provider
        self.contents: list[str | None] = []

    def model_limits(self, model: str) -> ModelLimits:
        return self._provider.model_limits(model)

    async def complete_json(
        self, *, messages: Sequence[Message], model: str, max_tokens: int, timeout_seconds: float
    ) -> ProviderResponse:
        self.contents.append(None)
        try:
            response = await self._provider.complete_json(
                messages=messages, model=model, max_tokens=max_tokens, timeout_seconds=timeout_seconds,
            )
        except ProviderFailure as failure:
            self.contents[-1] = failure.content
            raise
        self.contents[-1] = response.content
        return response


def _snapshot(model: StrictModel | None) -> dict | None:
    return None if model is None else model.model_dump(mode="json", by_alias=True)


def _graph_evidence(check: GraphCheck | None) -> dict | None:
    if check is None:
        return None
    return {
        "attempt_index": check.attempt_index,
        "proposal": _snapshot(check.proposal),
        "report": _snapshot(check.report),
        "limit": asdict(check.limit) if check.limit is not None else None,
    }


async def _write_validation_evidence(
    spec: SpecRevision,
    config: PlanningConfig,
    limits: ModelLimits,
    evidence_path: Path,
    provider: DeepSeekProvider,
    *,
    api_key: str,
    evidence_source: Literal["deepseek_live", "simulated_transport"],
) -> int:
    """使用内存记录单次 REAL 规划的各次尝试，返回技术结果退出码。"""
    if provider.mode is not PlanningMode.REAL or provider.fixture_id is not None:
        raise _InputError("验收要求 REAL Provider")
    async with provider:
        target = _external_evidence_path(evidence_path)
        snapshots = {"spec_revision": _snapshot(spec), "planning_config": _snapshot(config)}
        prompt = build_prompt(spec, config, validate_graph=True)
        recorder = _RecordingProvider(provider)
        # 在发出请求前独占创建，保护既有证据及同时启动的同名调用。
        with target.open("x", encoding="utf-8", errors="backslashreplace", newline="\n") as output:
            result = await generate_validated_proposal(spec, config, PlanningMode.REAL, recorder)
            evidence = {
                **snapshots,
                "input_hash": sha256_hex(snapshots),
                "evidence_source": evidence_source,
                "mode": PlanningMode.REAL,
                "model": config.model,
                "model_limits": asdict(limits),
                "initial_prompt": {"version": prompt.version, "hash": prompt.hash},
                "outcome": result.kind,
                "usage": _snapshot(result.usage),
                "attempts": [
                    {**asdict(item), "actual_usage": _snapshot(item.actual_usage), "content": content}
                    for item, content in zip(result.diagnostics, recorder.contents, strict=True)
                ],
                "proposal": _snapshot(result.proposal),
                "error": _snapshot(result.error),
                "graph_failure": result.graph_failure,
                "graph_check": _graph_evidence(result.graph_check),
                "latest_report_check": _graph_evidence(result.latest_report_check),
                "human_review": "pending",
            }
            serialized = json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False)
            if _contains_credential(serialized, api_key):
                raise _InputError("证据内容含凭据，已拒绝写入")
            output.write(serialized + "\n")
    return 0 if result.kind is ProposalKind.CANDIDATE else 1


def main(argv: Sequence[str] | None = None) -> int:
    """未启用、配置无效及本地故障返回 2，技术结果见证据。"""
    try:
        args = _parse_args(argv)
        if not args.enable_real:
            raise _InputError("真实验收默认关闭，请显式添加 --enable-real")
        if not all((args.spec, args.config, args.evidence, args.api_key_env)) or (
            args.context_tokens is None or args.max_output_tokens is None
        ):
            raise _InputError("真实验收缺少配置，请使用 --help")
        limits = ModelLimits(args.context_tokens, args.max_output_tokens)
        spec = SpecRevision.model_validate_json(_read_input(args.spec), strict=True)
        config = PlanningConfig.model_validate_json(_read_input(args.config), strict=True)
        if spec.hash != content_hash(spec.content):
            raise _InputError("SpecRevision.hash 与规格内容不一致")
        evidence_path = _external_evidence_path(args.evidence)
        api_key = getenv(args.api_key_env)
        if not api_key:
            raise _InputError("指定环境变量缺少凭据")
        if _contains_credential(spec.to_json(), api_key) or _contains_credential(config.to_json(), api_key):
            raise _InputError("输入含凭据")
        provider = DeepSeekProvider(api_key=api_key, allowed_models={config.model: limits})
        code = asyncio.run(_write_validation_evidence(
            spec, config, limits, evidence_path, provider, api_key=api_key, evidence_source="deepseek_live",
        ))
    except _InputError as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        # 模型校验、文件和 SDK 异常可能携带输入、路径或凭据。
        print("真实验收配置、输入或证据写入失败", file=sys.stderr)
        return 2
    if code == 0:
        print("技术候选通过图校验，人工复核待定")
    else:
        print("未得到可通过图校验的技术候选，请查看证据", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

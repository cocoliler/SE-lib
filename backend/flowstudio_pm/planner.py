"""运行一次有界 PM 结构化候选生成。"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from flowstudio_contracts import (
    PlanningConfig,
    PlanningMode,
    RunError,
    RunFailureCode,
    SpecRevision,
    TaskProposal,
    TokenUsage,
    canonical_json,
)
from flowstudio_contracts.codes import RETRYABLE_RUN_FAILURES
from flowstudio_contracts.constants import MAX_BODY_BYTES, MAX_OUTPUT_TOKENS, RETRY_BACKOFF_SECONDS

from .budget import BudgetError, RunBudget, aggregate_usage
from .parser import ProposalError, parse_proposal, with_blocking_questions
from .ports import LLMProvider
from .prompt import build_prompt
from .types import Message, ModelLimits, ProviderFailure, ProviderFailureKind, ProviderResponse


class ProposalKind(StrEnum):
    CANDIDATE = "CANDIDATE"
    NEEDS_INPUT = "NEEDS_INPUT"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class AttemptDiagnostic:
    """内存中的单次尝试摘要，保留散列和脱敏诊断。"""

    index: int
    prompt_version: str
    prompt_hash: str
    response_hash: str | None
    provider_request_id: str | None
    finish_reason: str | None
    elapsed_seconds: float
    reserved_tokens: int
    accounted_tokens: int
    actual_usage: TokenUsage | None
    usage_unknown: bool
    error_code: RunFailureCode | None
    provider_failure: ProviderFailureKind | None


@dataclass(frozen=True, slots=True)
class ProposalResult:
    """内部规划结果。CANDIDATE 只表示提案符合结构约束。"""

    kind: ProposalKind
    mode: PlanningMode
    fixture_id: str | None
    usage: TokenUsage
    diagnostics: tuple[AttemptDiagnostic, ...]
    proposal: TaskProposal | None = field(default=None, repr=False)
    error: RunError | None = None

    @property
    def attempt_count(self) -> int:
        return len(self.diagnostics)


_PROVIDER_CODES = {
    ProviderFailureKind.AUTH: RunFailureCode.MODEL_AUTH,
    ProviderFailureKind.RATE_LIMIT: RunFailureCode.MODEL_RATE_LIMITED,
    ProviderFailureKind.TIMEOUT: RunFailureCode.MODEL_TIMEOUT,
    ProviderFailureKind.NETWORK: RunFailureCode.MODEL_NETWORK,
    ProviderFailureKind.TRANSIENT_SERVER: RunFailureCode.MODEL_NETWORK,
    ProviderFailureKind.INVALID_RESPONSE: RunFailureCode.MODEL_SCHEMA,
}
_RETRYABLE_PROVIDER_FAILURES = {ProviderFailureKind.RATE_LIMIT, ProviderFailureKind.TRANSIENT_SERVER}
_BACKOFF_SECONDS = sum(RETRY_BACKOFF_SECONDS) / len(RETRY_BACKOFF_SECONDS)


def _message_bytes(messages: Sequence[Message]) -> int:
    return len(canonical_json(messages).encode("utf-8"))


def estimate_input_tokens(messages: Sequence[Message]) -> int:
    """用 UTF-8 消息字节及每条消息的固定开销做保守估算。"""
    return _message_bytes(messages) + 8 * len(messages)


def _run_error(
    code: RunFailureCode, message: str, request_id: str | None = None
) -> RunError:
    return RunError(
        code=code,
        message=message,
        provider_request_id=request_id,
        retryable=code in RETRYABLE_RUN_FAILURES,
    )


def _mode_matches(provider: LLMProvider, mode: PlanningMode, fixture_id: str | None) -> bool:
    if mode is PlanningMode.REAL:
        return provider.mode is mode and fixture_id is None and provider.fixture_id is None
    if mode is PlanningMode.TEST:
        return (
            provider.mode is mode and isinstance(fixture_id, str) and bool(fixture_id.strip())
            and fixture_id == provider.fixture_id
        )
    return False


def _response_hash(response: ProviderResponse | None) -> str | None:
    if response is None or response.content is None:
        return None
    # surrogatepass 只供散列编码。解析器仍拒绝包含孤立代理码点的回复。
    return hashlib.sha256(response.content.encode("utf-8", errors="surrogatepass")).hexdigest()


async def generate_proposal(
    spec: SpecRevision,
    config: PlanningConfig,
    mode: PlanningMode,
    provider: LLMProvider,
    *,
    fixture_id: str | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    estimate_input_tokens: Callable[[Sequence[Message]], int] = estimate_input_tokens,
) -> ProposalResult:
    """自开始执行起限时生成候选，调用方负责 Provider 生命周期与后续图校验。"""
    budget = RunBudget(monotonic)
    diagnostics: list[AttemptDiagnostic] = []

    def result(
        *, proposal: TaskProposal | None = None, error: RunError | None = None
    ) -> ProposalResult:
        kind = ProposalKind.FAILED
        if proposal is not None:
            kind = ProposalKind.NEEDS_INPUT if proposal.is_blocked else ProposalKind.CANDIDATE
        return ProposalResult(
            kind=kind,
            mode=mode,
            fixture_id=fixture_id,
            usage=aggregate_usage([item.actual_usage for item in diagnostics]),
            diagnostics=tuple(diagnostics),
            proposal=proposal,
            error=error,
        )

    if not _mode_matches(provider, mode, fixture_id):
        return result(error=_run_error(RunFailureCode.INTERNAL_ERROR, "规划模式与 Provider 或 fixture 不匹配"))
    model = config.model
    try:
        limits = provider.model_limits(model)
        if not isinstance(limits, ModelLimits):
            raise ValueError("模型限额无效")
        initial_prompt = build_prompt(spec, config)
    except (ValueError, TypeError):
        return result(error=_run_error(RunFailureCode.INTERNAL_ERROR, "规划模型配置或输入快照无效"))

    output_tokens = min(MAX_OUTPUT_TOKENS, limits.max_output_tokens)
    prompt = initial_prompt
    transport_retried = False
    last_error: RunError | None = None
    last_request_id: str | None = None
    while budget.has_attempts:
        try:
            budget.check_deadline()
            messages = prompt.messages
            if _message_bytes(messages) > MAX_BODY_BYTES:
                raise BudgetError(RunFailureCode.MODEL_BUDGET, "规划输入超出消息大小上限")
            prompt_hash = prompt.hash
            reserved, timeout = budget.reserve(estimate_input_tokens(messages), output_tokens, limits)
        except BudgetError as error:
            return result(error=_run_error(error.code, str(error), last_request_id))
        except (TypeError, ValueError):
            return result(error=_run_error(RunFailureCode.INTERNAL_ERROR, "无法计算规划输入预算"))

        started = monotonic()
        request_timeout = asyncio.timeout(timeout)
        response = None
        failure = None
        attempt_error = None
        try:
            async with request_timeout:
                response = await provider.complete_json(
                    messages=messages, model=model, max_tokens=output_tokens, timeout_seconds=timeout
                )
        except ProviderFailure as error:
            failure = error
        except TimeoutError:
            failure = ProviderFailure(ProviderFailureKind.TIMEOUT)
        except Exception:
            attempt_error = _run_error(RunFailureCode.INTERNAL_ERROR, "模型 Provider 调用异常")

        request_late = request_timeout.expired() or monotonic() - started >= timeout
        request_id = response.request_id if response is not None else failure.request_id if failure is not None else None
        actual_usage = response.usage if response is not None else failure.usage if failure is not None else None
        accounted, usage_unknown = budget.settle(reserved, actual_usage)
        proposal = None
        repair_error = None
        try:
            budget.check_deadline()
            budget.check_accounted_tokens()
            if request_late:
                raise BudgetError(RunFailureCode.MODEL_TIMEOUT, '模型请求已达到单次截止时间')
            if failure is not None:
                attempt_error = _run_error(_PROVIDER_CODES[failure.kind], str(failure), request_id)
            elif response is not None:
                proposal = with_blocking_questions(parse_proposal(response))
        except ProposalError as error:
            repair_error = error
            attempt_error = _run_error(error.code, str(error), request_id)
        except BudgetError as error:
            attempt_error = _run_error(error.code, str(error), request_id)

        response_hash = _response_hash(response)
        try:
            budget.check_deadline()
        except BudgetError as error:
            attempt_error = _run_error(error.code, str(error), request_id)
            repair_error = None
        diagnostics.append(AttemptDiagnostic(
            index=budget.attempt_count,
            prompt_version=prompt.version,
            prompt_hash=prompt_hash,
            response_hash=response_hash,
            provider_request_id=request_id,
            finish_reason=response.finish_reason if response is not None else None,
            elapsed_seconds=monotonic() - started,
            reserved_tokens=reserved,
            accounted_tokens=accounted,
            actual_usage=actual_usage,
            usage_unknown=usage_unknown,
            error_code=attempt_error.code if attempt_error is not None else None,
            provider_failure=failure.kind if failure is not None else None,
        ))
        if attempt_error is None and proposal is not None:
            return result(proposal=proposal)
        if attempt_error is None:
            return result(error=_run_error(RunFailureCode.INTERNAL_ERROR, "模型 Provider 未返回有效响应"))

        last_error = attempt_error
        last_request_id = request_id
        if not budget.has_attempts:
            break
        if repair_error is not None and response is not None:
            prompt = initial_prompt.with_repair(response, repair_error)
            continue
        if (
            failure is None or transport_retried
            or failure.kind not in _RETRYABLE_PROVIDER_FAILURES
            or attempt_error.code is not _PROVIDER_CODES[failure.kind]
        ):
            break
        transport_retried = True
        remaining = budget.remaining_seconds
        if remaining <= _BACKOFF_SECONDS:
            return result(error=_run_error(RunFailureCode.MODEL_TIMEOUT, "剩余时间不足以重试模型请求", request_id))
        try:
            async with asyncio.timeout(remaining):
                await sleep(_BACKOFF_SECONDS)
        except TimeoutError:
            return result(error=_run_error(RunFailureCode.MODEL_TIMEOUT, "规划等待重试时达到总截止时间", request_id))

    return result(error=last_error)

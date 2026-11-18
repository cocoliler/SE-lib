"""TEST fixture Provider：从 fixtures 目录读取 TaskProposal JSON。

这是 C（PM Agent）落地前的可运行占位：TEST 必须是用户明确选择的 fixture，
未知 fixture 在 API 层直接 422，不会静默伪造结果。
"""

from __future__ import annotations

import json
from pathlib import Path

from flowstudio_contracts import (
    PlanningConfig,
    PlanningMode,
    RunError,
    SpecRevision,
    TaskProposal,
    sha256_hex,
)
from flowstudio_contracts.codes import RETRYABLE_RUN_FAILURES
from flowstudio_pm.parser import ProposalError, with_blocking_questions

from .base import AttemptRecord, PlanningOutcome


class FixtureNotFound(Exception):
    pass


def normalize_fixture_proposal(proposal: TaskProposal) -> tuple[TaskProposal | None, RunError | None]:
    """TEST 与 REAL 复用同一关键假设问句规则；达到契约容量时返回可读取的失败。"""
    if not proposal.critical_assumption_ids:
        return proposal, None
    try:
        return with_blocking_questions(proposal), None
    except ProposalError as exc:
        return None, RunError(code=exc.code, message=str(exc), retryable=exc.code in RETRYABLE_RUN_FAILURES)


class FixtureEngine:
    def __init__(self, fixtures_dir: Path | None) -> None:
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else None

    def fixtures(self) -> tuple[str, ...]:
        if self.fixtures_dir is None or not self.fixtures_dir.is_dir():
            return ()
        return tuple(sorted(path.stem for path in self.fixtures_dir.glob("*.json")))

    def plan(
        self,
        *,
        mode: PlanningMode,
        spec_revision: SpecRevision,
        config: PlanningConfig,
        fixture_id: str | None,
        run_id: str,
    ) -> PlanningOutcome:
        if fixture_id is None:
            raise FixtureNotFound("TEST 模式必须提供 fixture_id")
        path = (self.fixtures_dir / f"{fixture_id}.json") if self.fixtures_dir else None
        if path is None or not path.is_file():
            raise FixtureNotFound(f"未知 fixture：{fixture_id}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        proposal = TaskProposal.model_validate(raw)
        request_hash = sha256_hex(
            {
                "run_id": run_id,
                "fixture_id": fixture_id,
                "spec_revision_id": str(spec_revision.id),
                "config": config.model_dump(mode="json", by_alias=True),
            }
        )
        candidate, error = normalize_fixture_proposal(proposal)
        return PlanningOutcome(
            proposal=candidate,
            error=error,
            attempts=[
                AttemptRecord(
                    attempt_no=1,
                    request_hash=request_hash,
                    response=proposal.model_dump(mode="json", by_alias=True),
                    usage={"total_tokens": 0},
                    error={"code": error.code.value} if error else None,
                )
            ],
        )

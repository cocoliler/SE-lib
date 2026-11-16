"""规划引擎端口。

PM 的职责边界：理解规格、提出任务；不决定合法性（由 T05 纯函数编排器决定），不执行工具。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from flowstudio_contracts import (
    PlanningConfig,
    PlanningMode,
    RunError,
    SpecRevision,
    TaskProposal,
    TokenUsage,
)


@dataclass
class AttemptRecord:
    attempt_no: int
    request_hash: str
    response: dict | None = None
    usage: dict | None = None
    error: dict | None = None


@dataclass
class PlanningOutcome:
    proposal: TaskProposal | None = None
    error: RunError | None = None
    usage: TokenUsage | None = None
    attempts: list[AttemptRecord] = field(default_factory=list)


class PlanningEngine(Protocol):
    def fixtures(self) -> tuple[str, ...]:
        """可用 TEST fixture 的 ID 列表。"""

    def plan(
        self,
        *,
        mode: PlanningMode,
        spec_revision: SpecRevision,
        config: PlanningConfig,
        fixture_id: str | None,
        run_id: str,
    ) -> PlanningOutcome:
        """执行一次规划（可能包含内部有界修复）。同步调用，不持有数据库事务。"""

"""规划运行契约：PlanningPolicy / PlanningConfig / PlanningRun 与失败诊断。"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from .base import BodyText, Identifier, StrictModel, UtcTimestamp, Uuid, duplicates, enum_value, text
from .codes import RETRYABLE_RUN_FAILURES, RunFailureCode
from .constants import MAX_PLANNING_ATTEMPTS, MAX_SPEC_CONSTRAINTS
from .tasks import TaskProposal
from .validation import ValidationReport


class Granularity(StrEnum):
    COARSE = "coarse"
    STANDARD = "standard"
    FINE = "fine"


class PlanningMode(StrEnum):
    REAL = "REAL"
    TEST = "TEST"


class PlanningStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    NEEDS_INPUT = "NEEDS_INPUT"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in (PlanningStatus.SUCCEEDED, PlanningStatus.NEEDS_INPUT, PlanningStatus.FAILED)


class StageEdge(StrictModel):
    """允许的阶段迁移 from→to；JSON 字段名为 from/to。"""

    from_stage: Identifier = Field(alias="from")
    to_stage: Identifier = Field(alias="to")

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class PlanningPolicy(StrictModel):
    """可选过程约束；null 表示不额外限制，缺省即通用规则。"""

    schema_version: Literal["1.0"]
    rules_version: Literal["1.0"]
    allowed_stages: list[Identifier] | None
    allowed_roles: list[Identifier] | None
    allowed_categories: list[Identifier] | None
    allowed_stage_edges: list[StageEdge] | None
    required_categories: list[Identifier]

    @model_validator(mode="after")
    def _consistent_constraints(self) -> PlanningPolicy:
        for name in ("allowed_stages", "allowed_roles", "allowed_categories", "required_categories"):
            values = getattr(self, name)
            if values is None:
                continue
            repeated = duplicates(values)
            if repeated:
                raise ValueError(f"policy.{name} 存在重复值：{sorted(repeated)}")
        if self.allowed_stage_edges is not None:
            pairs = [(edge.from_stage, edge.to_stage) for edge in self.allowed_stage_edges]
            repeated_pairs = duplicates(pairs)
            if repeated_pairs:
                raise ValueError(f"policy.allowed_stage_edges 存在重复迁移：{sorted(repeated_pairs)}")
            if self.allowed_stages is not None:
                allowed = set(self.allowed_stages)
                stray = {stage for pair in pairs for stage in pair} - allowed
                if stray:
                    raise ValueError(f"allowed_stage_edges 引用了未允许的阶段：{sorted(stray)}")
        if self.allowed_categories is not None:
            stray_categories = set(self.required_categories) - set(self.allowed_categories)
            if stray_categories:
                raise ValueError(f"required_categories 不在 allowed_categories 中：{sorted(stray_categories)}")
        return self


class PlanningConfig(StrictModel):
    """请求侧规划参数；服务端解析模型别名后写入快照。"""

    model: text(1, 120)
    granularity: enum_value(Granularity)
    planning_constraints: Annotated[list[BodyText], Field(max_length=MAX_SPEC_CONSTRAINTS)]
    policy: PlanningPolicy | None = None


class TokenUsage(StrictModel):
    prompt_tokens: Annotated[int, Field(ge=0)] | None = None
    completion_tokens: Annotated[int, Field(ge=0)] | None = None
    total_tokens: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def _total_matches(self) -> TokenUsage:
        parts = (self.prompt_tokens, self.completion_tokens)
        if all(part is not None for part in parts) and self.total_tokens is not None:
            if self.total_tokens != self.prompt_tokens + self.completion_tokens:  # type: ignore[operator]
                raise ValueError("total_tokens 必须等于 prompt_tokens + completion_tokens")
        return self


class RunError(StrictModel):
    """规划失败诊断；retryable 必须与失败码的可重试集合一致。"""

    code: enum_value(RunFailureCode)
    message: BodyText
    provider_request_id: text(1, 200) | None = None
    retryable: bool

    @model_validator(mode="after")
    def _retryable_matches_code(self) -> RunError:
        expected = self.code in RETRYABLE_RUN_FAILURES
        if self.retryable is not expected:
            raise ValueError(f"{self.code} 的 retryable 必须为 {expected}")
        return self


class PlanningRun(StrictModel):
    """单次规划请求。SUCCEEDED 只表示候选通过结构/图校验，不代表已保存或已执行。"""

    id: Uuid
    spec_revision_id: Uuid
    mode: enum_value(PlanningMode)
    status: enum_value(PlanningStatus)
    config_snapshot: PlanningConfig
    attempt_count: Annotated[int, Field(ge=0, le=MAX_PLANNING_ATTEMPTS)]
    fixture_id: Identifier | None = None
    usage: TokenUsage | None = None
    error: RunError | None = None
    proposal: TaskProposal | None = None
    validation_report: ValidationReport | None = None
    created_at: UtcTimestamp
    started_at: UtcTimestamp | None = None
    finished_at: UtcTimestamp | None = None

    @model_validator(mode="after")
    def _status_consistency(self) -> PlanningRun:
        if self.mode is PlanningMode.REAL and self.fixture_id is not None:
            raise ValueError("REAL 模式禁止提交 fixture_id")
        if self.mode is PlanningMode.TEST and self.fixture_id is None:
            raise ValueError("TEST 模式必须指定 fixture_id")
        if self.status is PlanningStatus.SUCCEEDED:
            if self.proposal is None or self.validation_report is None:
                raise ValueError("SUCCEEDED 必须同时包含 proposal 与 validation_report")
            if not self.validation_report.valid:
                raise ValueError("SUCCEEDED 的 validation_report.valid 必须为 true")
            if self.proposal.critical_assumption_ids:
                raise ValueError("存在 critical 假设时必须为 NEEDS_INPUT，不能标记 SUCCEEDED")
            if self.error is not None:
                raise ValueError("SUCCEEDED 不允许携带 error")
        if self.status is PlanningStatus.NEEDS_INPUT:
            if self.proposal is None or not self.proposal.blocking_questions:
                raise ValueError("NEEDS_INPUT 必须包含带 blocking_questions 的 proposal")
        if self.status is PlanningStatus.FAILED and self.error is None:
            raise ValueError("FAILED 必须包含 error 诊断")
        if self.status in (PlanningStatus.QUEUED, PlanningStatus.RUNNING) and self.finished_at is not None:
            raise ValueError("未终结的运行不能有 finished_at")
        return self


class PlanningRunCreated(StrictModel):
    id: Uuid
    status: Literal["QUEUED"]
    poll_url: text(1, 300)


__all__ = [
    "Granularity",
    "PlanningConfig",
    "PlanningMode",
    "PlanningPolicy",
    "PlanningRun",
    "PlanningRunCreated",
    "PlanningStatus",
    "RunError",
    "StageEdge",
    "TokenUsage",
]

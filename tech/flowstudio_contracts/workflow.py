"""工作流与版本契约：SpecRevision、PlanRevision、派生结果、布局与导出包。"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import BodyText, Identifier, Sha256Hex, StrictModel, UtcTimestamp, Uuid, enum_value, text
from .constants import MAX_EDGES, MAX_ISSUE_REFS, MAX_TASKS
from .planning import PlanningPolicy
from .spec import DesignSpecContent
from .tasks import Task
from .validation import TaskEdge, ValidationReport


class PlanSource(StrEnum):
    AI = "AI"
    TEST = "TEST"
    MANUAL = "MANUAL"


class OriginMode(StrEnum):
    REAL = "REAL"
    TEST = "TEST"
    NONE = "NONE"


class Project(StrictModel):
    id: Uuid
    name: text(1, 120)
    archived_at: UtcTimestamp | None
    created_at: UtcTimestamp


class SpecRevision(StrictModel):
    """不可变规格版本；revision 从 1 递增，hash 为内容规范化 SHA-256。"""

    id: Uuid
    spec_id: Uuid
    revision: Annotated[int, Field(ge=1)]
    content: DesignSpecContent
    hash: Sha256Hex
    created_at: UtcTimestamp


class ExecutionStage(StrictModel):
    """业务阶段分组：来自任务的 stage 标签，不隐式产生依赖。"""

    stage_id: Identifier
    task_ids: Annotated[list[Identifier], Field(min_length=1, max_length=MAX_TASKS)]


class PlanDerivation(StrictModel):
    """编排器纯函数输出；客户端投影只消费这些派生字段。"""

    input_hash: Sha256Hex
    edges: Annotated[list[TaskEdge], Field(max_length=MAX_EDGES)]
    execution_stages: Annotated[list[ExecutionStage], Field(max_length=MAX_TASKS)]
    parallel_batches: Annotated[list[list[Identifier]], Field(max_length=MAX_TASKS)]
    ordered_task_ids: Annotated[list[Identifier], Field(max_length=MAX_TASKS)]
    validation_report: ValidationReport


class PlanRevision(StrictModel):
    """不可变计划版本；冻结假设确认与来源，派生字段由服务端重算。"""

    id: Uuid
    plan_id: Uuid
    revision: Annotated[int, Field(ge=1)]
    spec_revision_id: Uuid
    planning_run_id: Uuid | None
    parent_revision_id: Uuid | None
    policy_snapshot: PlanningPolicy | None
    source: enum_value(PlanSource)
    origin_mode: enum_value(OriginMode)
    confirmed_assumption_ids: Annotated[list[Identifier], Field(max_length=MAX_ISSUE_REFS)]
    tasks: Annotated[list[Task], Field(min_length=1, max_length=MAX_TASKS)]
    edges: Annotated[list[TaskEdge], Field(max_length=MAX_EDGES)]
    execution_stages: Annotated[list[ExecutionStage], Field(max_length=MAX_TASKS)]
    parallel_batches: Annotated[list[list[Identifier]], Field(max_length=MAX_TASKS)]
    ordered_task_ids: Annotated[list[Identifier], Field(max_length=MAX_TASKS)]
    validation_report: ValidationReport
    hash: Sha256Hex
    created_at: UtcTimestamp

    @model_validator(mode="after")
    def _immutable_invariants(self) -> PlanRevision:
        if not self.validation_report.valid:
            raise ValueError("PlanRevision 只能保存通过校验的计划")
        if len(self.confirmed_assumption_ids) != len(set(self.confirmed_assumption_ids)):
            raise ValueError("confirmed_assumption_ids 存在重复")
        if self.origin_mode is OriginMode.NONE:
            if self.source is not PlanSource.MANUAL or self.planning_run_id is not None:
                raise ValueError("origin_mode=NONE 必须是 MANUAL 且不携带 planning_run_id")
        elif self.planning_run_id is None:
            raise ValueError("origin_mode=REAL/TEST 必须携带 planning_run_id")
        if self.source is PlanSource.TEST and self.origin_mode is not OriginMode.TEST:
            raise ValueError("source=TEST 必须来自 TEST 运行，不能改写来源")
        if self.source is PlanSource.AI and self.origin_mode is not OriginMode.REAL:
            raise ValueError("source=AI 必须来自 REAL 运行")
        return self


class PlanRevisionSummary(StrictModel):
    """历史列表项：不含任务正文，只给出可导航的版本信息。"""

    id: Uuid
    plan_id: Uuid
    revision: Annotated[int, Field(ge=1)]
    spec_revision_id: Uuid
    source: enum_value(PlanSource)
    origin_mode: enum_value(OriginMode)
    hash: Sha256Hex
    created_at: UtcTimestamp


class Position(StrictModel):
    x: Annotated[float, Field(allow_inf_nan=False)]
    y: Annotated[float, Field(allow_inf_nan=False)]


class CanvasNote(StrictModel):
    """画布注释：只参与显示，不参与业务顺序与覆盖率。"""

    id: Identifier
    text: text(0, 2000)
    x: Annotated[float, Field(allow_inf_nan=False)]
    y: Annotated[float, Field(allow_inf_nan=False)]
    color: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None


class Viewport(StrictModel):
    x: Annotated[float, Field(allow_inf_nan=False)]
    y: Annotated[float, Field(allow_inf_nan=False)]
    zoom: Annotated[float, Field(gt=0, allow_inf_nan=False)]


class Layout(StrictModel):
    """独立可更新的画布布局；不改变计划 hash。"""

    plan_revision_id: Uuid
    revision: Annotated[int, Field(ge=0)]
    positions: dict[Identifier, Position]
    notes: Annotated[list[CanvasNote], Field(max_length=MAX_ISSUE_REFS)]
    viewport: Viewport


class ExportBundle(StrictModel):
    """导出包：附带规格与规划约束快照，便于离线解释计划来源。"""

    schema_version: Literal["1.0"]
    spec_snapshot: DesignSpecContent
    policy_snapshot: PlanningPolicy | None
    plan_revision: PlanRevision
    layout: Layout | None


__all__ = [
    "CanvasNote",
    "ExecutionStage",
    "ExportBundle",
    "Layout",
    "OriginMode",
    "PlanDerivation",
    "PlanRevision",
    "PlanRevisionSummary",
    "PlanSource",
    "Position",
    "Project",
    "SpecRevision",
    "TaskEdge",
    "Viewport",
]

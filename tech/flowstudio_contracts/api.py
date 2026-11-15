"""HTTP 接口契约：请求/响应 DTO、错误体、分页与 operation 表。

operation 表是 OpenAPI 的唯一定义来源；FastAPI 路由实现后由契约漂移测试比对，
避免"文档一套、路由一套"。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field, model_validator

from .base import BodyText, Identifier, StrictModel, Uuid, enum_value, text
from .codes import ErrorCode
from .constants import API_PREFIX, PAGE_SIZE_MAX
from .planning import PlanningConfig, PlanningMode, PlanningPolicy, PlanningRun, PlanningRunCreated
from .spec import DesignSpecContent
from .tasks import Task
from .validation import Issue, ValidationReport
from .workflow import (
    CanvasNote,
    ExportBundle,
    Layout,
    PlanDerivation,
    PlanRevision,
    PlanRevisionSummary,
    Position,
    Project,
    SpecRevision,
    Viewport,
)


class CreateProjectRequest(StrictModel):
    name: text(1, 120)


class SpecRevisionWriteRequest(StrictModel):
    """expected_revision 即 CAS 期望值：初次保存为 0，冲突返回 409。"""

    expected_revision: Annotated[int, Field(ge=0)]
    content: DesignSpecContent


class SpecValidationRequest(StrictModel):
    content: DesignSpecContent


class CreatePlanningRunRequest(StrictModel):
    spec_revision_id: Uuid
    mode: enum_value(PlanningMode)
    config: PlanningConfig
    fixture_id: Identifier | None = None

    @model_validator(mode="after")
    def _mode_matches_fixture(self) -> CreatePlanningRunRequest:
        if self.mode is PlanningMode.TEST and self.fixture_id is None:
            raise ValueError("TEST 模式必须指定 fixture_id")
        if self.mode is PlanningMode.REAL and self.fixture_id is not None:
            raise ValueError("REAL 模式禁止 fixture_id")
        return self


class OrchestrationRequest(StrictModel):
    spec_revision_id: Uuid
    policy: PlanningPolicy | None = None
    tasks: Annotated[list[Task], Field(min_length=1)]


class WorkflowValidationRequest(OrchestrationRequest):
    """与编排请求同形状：复用同一 build，不复制规则。"""


class SavePlanRequest(StrictModel):
    """保存计划只提交任务与来源；派生字段与 source 由服务端推导。"""

    spec_revision_id: Uuid
    planning_run_id: Uuid | None = None
    policy: PlanningPolicy | None = None
    tasks: Annotated[list[Task], Field(min_length=1)]
    confirmed_assumption_ids: list[Identifier]
    layout: Layout | None = None


class SavePlanRevisionRequest(SavePlanRequest):
    expected_revision: Annotated[int, Field(ge=1)]
    parent_revision_id: Uuid | None = None


class LayoutWriteRequest(StrictModel):
    expected_revision: Annotated[int, Field(ge=0)]
    positions: dict[Identifier, Position]
    notes: Annotated[list[CanvasNote], Field(max_length=200)]
    viewport: Viewport


class SavePlanResponse(StrictModel):
    plan_id: Uuid
    revision: PlanRevision


class PlanningRunTasksResponse(StrictModel):
    tasks: list[Task]


class ProjectPage(StrictModel):
    items: list[Project]
    next_cursor: text(1, 200) | None


class SpecRevisionPage(StrictModel):
    items: list[SpecRevision]
    next_cursor: text(1, 200) | None


class PlanRevisionSummaryPage(StrictModel):
    items: list[PlanRevisionSummary]
    next_cursor: text(1, 200) | None


class ApiError(StrictModel):
    """错误体：issues 复用 ValidationReport 的缺陷定位结构。"""

    code: enum_value(ErrorCode)
    message: BodyText
    issues: list[Issue]
    request_id: text(1, 200)


class ErrorEnvelope(StrictModel):
    error: ApiError


PAGE_PARAMETERS = (
    ("limit", "每页数量，默认 20，最大 100"),
    ("cursor", "不透明分页游标"),
)

RULES_VERSION_HEADER = "X-Rules-Version"


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    operation_id: str
    summary: str
    success_status: int
    response_model: type[StrictModel] | None
    request_model: type[StrictModel] | None = None
    parameters: tuple[tuple[str, str], ...] = ()
    error_codes: tuple[ErrorCode, ...] = ()
    tags: tuple[str, ...] = ()


OPERATIONS: tuple[Operation, ...] = (
    Operation("post", "/projects", "createProject", "创建本地项目", 201, Project, CreateProjectRequest,
              error_codes=(ErrorCode.VALIDATION_FAILED,), tags=("projects",)),
    Operation("get", "/projects", "listProjects", "分页读取项目", 200, ProjectPage, None, PAGE_PARAMETERS,
              tags=("projects",)),
    Operation("post", "/projects/{project_id}/spec-revisions", "createSpecRevision", "保存不可变规格版本", 201,
              SpecRevision, SpecRevisionWriteRequest,
              error_codes=(ErrorCode.VALIDATION_FAILED, ErrorCode.REVISION_CONFLICT), tags=("specs",)),
    Operation("get", "/projects/{project_id}/spec-revisions", "listSpecRevisions", "分页读取规格版本", 200,
              SpecRevisionPage, None, PAGE_PARAMETERS, tags=("specs",)),
    Operation("get", "/spec-revisions/{revision_id}", "getSpecRevision", "读取单个规格版本", 200, SpecRevision,
              error_codes=(ErrorCode.NOT_FOUND,), tags=("specs",)),
    Operation("post", "/spec-validations", "validateSpec", "结构与确定性问题检查，不调用模型", 200,
              ValidationReport, SpecValidationRequest,
              error_codes=(ErrorCode.VALIDATION_FAILED,), tags=("specs",)),
    Operation("post", "/planning-runs", "createPlanningRun", "入队一次规划请求", 202, PlanningRunCreated,
              CreatePlanningRunRequest,
              error_codes=(ErrorCode.VALIDATION_FAILED, ErrorCode.QUEUE_FULL), tags=("planning",)),
    Operation("get", "/planning-runs/{run_id}", "getPlanningRun", "查询规划运行与诊断", 200, PlanningRun,
              error_codes=(ErrorCode.NOT_FOUND,), tags=("planning",)),
    Operation("get", "/planning-runs/{run_id}/tasks", "getPlanningRunTasks", "读取已通过校验的候选任务", 200,
              PlanningRunTasksResponse,
              error_codes=(ErrorCode.NOT_FOUND, ErrorCode.RESULT_NOT_READY), tags=("planning",)),
    Operation("post", "/orchestrations", "orchestratePlan", "确定性拓扑分层与并行批次", 200, PlanDerivation,
              OrchestrationRequest,
              error_codes=(ErrorCode.VALIDATION_FAILED, ErrorCode.NOT_FOUND), tags=("orchestration",)),
    Operation("post", "/workflow-validations", "validateWorkflow", "仅返回校验报告", 200, ValidationReport,
              WorkflowValidationRequest,
              error_codes=(ErrorCode.VALIDATION_FAILED, ErrorCode.NOT_FOUND), tags=("orchestration",)),
    Operation("post", "/projects/{project_id}/plans", "createPlan", "保存首个计划版本", 201, SavePlanResponse,
              SavePlanRequest,
              error_codes=(ErrorCode.VALIDATION_FAILED, ErrorCode.NOT_FOUND), tags=("plans",)),
    Operation("post", "/plans/{plan_id}/revisions", "createPlanRevision", "保存新计划版本（CAS）", 201,
              PlanRevision, SavePlanRevisionRequest,
              error_codes=(ErrorCode.VALIDATION_FAILED, ErrorCode.REVISION_CONFLICT,
                           ErrorCode.IDEMPOTENCY_CONFLICT), tags=("plans",)),
    Operation("get", "/plans/{plan_id}/revisions", "listPlanRevisions", "分页读取计划历史", 200,
              PlanRevisionSummaryPage, None, PAGE_PARAMETERS, tags=("plans",)),
    Operation("get", "/plan-revisions/{revision_id}", "getPlanRevision", "读取计划版本全文", 200, PlanRevision,
              error_codes=(ErrorCode.NOT_FOUND,), tags=("plans",)),
    Operation("get", "/plan-revisions/{revision_id}/layout", "getLayout", "读取画布布局", 200, Layout,
              error_codes=(ErrorCode.NOT_FOUND,), tags=("layout",)),
    Operation("put", "/plan-revisions/{revision_id}/layout", "putLayout", "独立更新画布布局", 200, Layout,
              LayoutWriteRequest,
              error_codes=(ErrorCode.VALIDATION_FAILED, ErrorCode.REVISION_CONFLICT), tags=("layout",)),
    Operation("get", "/plan-revisions/{revision_id}/export", "exportPlanRevision", "导出计划包与快照", 200,
              ExportBundle, None, (("format", "导出格式，当前仅 json"),),
              error_codes=(ErrorCode.NOT_FOUND,), tags=("plans",)),
)


def operation_path(operation: Operation) -> str:
    return f"{API_PREFIX}{operation.path}"


def request_id_example() -> str:
    return "00000000-0000-4000-8000-000000000000"


__all__ = [
    "ApiError",
    "CreatePlanningRunRequest",
    "CreateProjectRequest",
    "ErrorEnvelope",
    "LayoutWriteRequest",
    "Operation",
    "OrchestrationRequest",
    "PAGE_PARAMETERS",
    "PAGE_SIZE_MAX",
    "OPERATIONS",
    "PlanningRunTasksResponse",
    "PlanRevisionSummaryPage",
    "ProjectPage",
    "RULES_VERSION",
    "SavePlanRequest",
    "SavePlanResponse",
    "SavePlanRevisionRequest",
    "SpecRevisionPage",
    "SpecRevisionWriteRequest",
    "SpecValidationRequest",
    "WorkflowValidationRequest",
    "operation_path",
    "request_id_example",
]

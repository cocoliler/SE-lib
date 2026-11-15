"""契约样例：覆盖规格、候选、运行、计划、布局与错误体的 TEST 夹具。

这些样例用于契约测试、前端 mock 与 `fixture_id` 显式选择，不是产品模板库，
也不参与默认规划：PM Agent 只能由规格内容生成候选。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Final
from uuid import UUID

from .api import ApiError, ErrorEnvelope
from .base import canonical_json, sha256_hex
from .codes import ErrorCode, IssueCode, RunFailureCode
from .constants import RULES_VERSION
from .planning import (
    Granularity,
    PlanningConfig,
    PlanningMode,
    PlanningRun,
    PlanningStatus,
    RunError,
    TokenUsage,
)
from .spec import DesignSpecContent, Requirement, RequirementKind, RequirementPriority
from .tasks import (
    AssumptionImpact,
    Deliverable,
    EstimatedEffort,
    SpecInput,
    Task,
    TaskAssumption,
    TaskInput,
    TaskPriority,
    TaskProposal,
)
from .validation import Coverage, Issue, IssueSeverity, TaskEdge, ValidationReport
from .workflow import (
    CanvasNote,
    ExecutionStage,
    Layout,
    OriginMode,
    PlanDerivation,
    PlanRevision,
    PlanSource,
    Position,
    Viewport,
)

SAMPLE_TIME: Final[datetime] = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)
PROJECT_ID: Final[UUID] = UUID("11111111-1111-4111-8111-111111111111")
SPEC_ID: Final[UUID] = UUID("22222222-2222-4222-8222-222222222222")
SPEC_REVISION_ID: Final[UUID] = UUID("33333333-3333-4333-8333-333333333333")
PLANNING_RUN_ID: Final[UUID] = UUID("44444444-4444-4444-8444-444444444444")
PLAN_ID: Final[UUID] = UUID("55555555-5555-4555-8555-555555555555")
PLAN_REVISION_ID: Final[UUID] = UUID("66666666-6666-4666-8666-666666666666")
REQUEST_ID: Final[str] = "77777777-7777-4777-8777-777777777777"


def sample_design_spec() -> DesignSpecContent:
    return DesignSpecContent(
        schema_version="1.0",
        product_name="契约样例产品",
        background="用于演示通用规格输入；不绑定具体行业，也不代表任何真实产品。",
        goals=["验证规格字段可被结构化保存", "验证需求可被任务覆盖"],
        target_users=["产品负责人", "开发人员"],
        requirements=[
            Requirement(
                id="R-01",
                kind=RequirementKind.FUNCTIONAL,
                text="用户可以创建并保存一条记录。",
                priority=RequirementPriority.MUST,
                acceptance_criteria=["保存后返回稳定 ID", "重复提交不产生重复记录"],
            ),
            Requirement(
                id="R-02",
                kind=RequirementKind.FUNCTIONAL,
                text="用户可以按关键字检索记录并查看详情。",
                priority=RequirementPriority.MUST,
                acceptance_criteria=["检索结果分页", "详情字段与保存内容一致"],
            ),
            Requirement(
                id="R-03",
                kind=RequirementKind.FUNCTIONAL,
                text="用户可以导出当前检索结果。",
                priority=RequirementPriority.COULD,
                acceptance_criteria=["导出格式为 JSON", "导出内容与当前筛选一致"],
            ),
            Requirement(
                id="NFR-01",
                kind=RequirementKind.NONFUNCTIONAL,
                text="所有写入请求必须拒绝未知字段。",
                priority=RequirementPriority.MUST,
                acceptance_criteria=["未知字段返回 422", "错误体包含字段路径"],
            ),
        ],
        technical_constraints=["本地单体部署", "仅使用 SQLite"],
        development_constraints=["四人以内协作", "两周内完成原型"],
        delivery_requirements=["可运行本地原型", "契约产物与模型一致"],
        acceptance_criteria=["主要流程可端到端演示", "契约漂移检查通过"],
        supplemental_text="样例正文；不含真实业务机密。",
        confirmed_assumptions=[],
    )


def _task(
    *,
    task_id: str,
    name: str,
    description: str,
    category: str,
    stage: str,
    priority: TaskPriority,
    role: str,
    dependencies: list[str],
    requirement_ids: list[str],
    deliverables: list[Deliverable],
    criteria: list[str],
    inputs: list[SpecInput | TaskInput] | None = None,
    assumptions: list[TaskAssumption] | None = None,
    effort: EstimatedEffort | None = None,
    rationale: str = "",
) -> Task:
    return Task(
        task_id=task_id,
        name=name,
        description=description,
        category=category,
        stage=stage,
        priority=priority,
        assigned_role=role,
        dependencies=dependencies,
        inputs=inputs or [],
        deliverables=deliverables,
        acceptance_criteria=criteria,
        source_requirement_ids=requirement_ids,
        rationale=rationale,
        assumptions=assumptions or [],
        estimated_effort=effort,
    )


def sample_tasks() -> list[Task]:
    return [
        _task(
            task_id="T-01",
            name="确认规格与验收口径",
            description="逐条确认需求、验收条件与约束，标出仍然模糊的地方。",
            category="discovery",
            stage="discovery",
            priority=TaskPriority.HIGH,
            role="analyst",
            dependencies=[],
            requirement_ids=["R-01", "R-02", "NFR-01"],
            deliverables=[Deliverable(id="D-01", text="确认后的需求清单与验收口径")],
            criteria=["每条 must 需求有验收条件", "遗留问题列入阻塞问题"],
            effort=EstimatedEffort(min_hours=2, max_hours=4, basis="按 4 条需求估算", is_estimate=True),
            rationale="规格是唯一输入，先固定验收口径避免后续返工。",
        ),
        _task(
            task_id="T-02",
            name="数据模型与接口契约",
            description="定义记录实体、字段约束与检索/导出接口结构。",
            category="design",
            stage="design",
            priority=TaskPriority.HIGH,
            role="architect",
            dependencies=["T-01"],
            requirement_ids=["R-01", "R-02", "NFR-01"],
            deliverables=[Deliverable(id="D-02", text="数据模型与接口契约文档")],
            criteria=["字段与约束可被校验", "未知字段处理明确"],
            inputs=[SpecInput(kind="spec", requirement_id="NFR-01"), TaskInput(kind="task", task_id="T-01", deliverable_id="D-01")],
            rationale="契约先行的前提是数据模型稳定。",
        ),
        _task(
            task_id="T-03",
            name="实现保存与检索接口",
            description="实现创建、保存与分页检索接口，并复用统一契约校验。",
            category="build",
            stage="build",
            priority=TaskPriority.HIGH,
            role="backend",
            dependencies=["T-02"],
            requirement_ids=["R-01", "R-02"],
            deliverables=[Deliverable(id="D-03", text="保存与检索接口及单测")],
            criteria=["重复提交幂等", "检索分页返回游标"],
            inputs=[TaskInput(kind="task", task_id="T-02", deliverable_id="D-02")],
            assumptions=[
                TaskAssumption(id="A-01", text="检索默认按创建时间倒序", impact=AssumptionImpact.LOW),
            ],
            rationale="需求 R-01/R-02 需要服务端能力支撑。",
        ),
        _task(
            task_id="T-04",
            name="实现列表与详情界面",
            description="实现检索、分页与详情展示，错误按字段路径定位。",
            category="build",
            stage="build",
            priority=TaskPriority.MEDIUM,
            role="frontend",
            dependencies=["T-02"],
            requirement_ids=["R-02", "NFR-01"],
            deliverables=[Deliverable(id="D-04", text="列表与详情界面")],
            criteria=["422 错误可定位到字段", "分页可前进后退"],
            inputs=[TaskInput(kind="task", task_id="T-02", deliverable_id="D-02")],
            rationale="界面消费同一 DTO，避免二次定义字段。",
        ),
        _task(
            task_id="T-05",
            name="导出与端到端验收",
            description="实现 JSON 导出并用样例数据跑通端到端验收。",
            category="verify",
            stage="verify",
            priority=TaskPriority.LOW,
            role="tester",
            dependencies=["T-03", "T-04"],
            requirement_ids=["R-03"],
            deliverables=[Deliverable(id="D-05", text="导出实现与验收记录")],
            criteria=["导出与筛选结果一致", "验收记录可复现"],
            inputs=[
                TaskInput(kind="task", task_id="T-03", deliverable_id="D-03"),
                TaskInput(kind="task", task_id="T-04", deliverable_id="D-04"),
            ],
            rationale="导出依赖已完成的检索与界面。",
        ),
    ]


def sample_task_proposal() -> TaskProposal:
    return TaskProposal(schema_version="1.0", tasks=sample_tasks(), blocking_questions=[])


def sample_blocked_proposal() -> TaskProposal:
    return TaskProposal(
        schema_version="1.0",
        tasks=[],
        blocking_questions=["规格未说明记录必须归属哪个用户，是否需要多租户隔离？"],
    )


def sample_derivation() -> PlanDerivation:
    spec = sample_design_spec()
    report = sample_validation_report()
    return PlanDerivation(
        input_hash=sha256_hex({"spec": spec.model_dump(mode="json"), "rules_version": RULES_VERSION}),
        edges=[
            TaskEdge(source="T-01", target="T-02"),
            TaskEdge(source="T-02", target="T-03"),
            TaskEdge(source="T-02", target="T-04"),
            TaskEdge(source="T-03", target="T-05"),
            TaskEdge(source="T-04", target="T-05"),
        ],
        execution_stages=[
            ExecutionStage(stage_id="discovery", task_ids=["T-01"]),
            ExecutionStage(stage_id="design", task_ids=["T-02"]),
            ExecutionStage(stage_id="build", task_ids=["T-03", "T-04"]),
            ExecutionStage(stage_id="verify", task_ids=["T-05"]),
        ],
        parallel_batches=[["T-01"], ["T-02"], ["T-03", "T-04"], ["T-05"]],
        ordered_task_ids=["T-01", "T-02", "T-03", "T-04", "T-05"],
        validation_report=report,
    )


def sample_validation_report() -> ValidationReport:
    spec = sample_design_spec()
    return ValidationReport(
        valid=True,
        errors=[],
        warnings=[],
        coverage=Coverage(covered_ids=spec.requirement_ids, uncovered_ids=[]),
        rules_version=RULES_VERSION,  # type: ignore[arg-type]
        input_hash=sha256_hex({"spec": spec.model_dump(mode="json"), "rules_version": RULES_VERSION}),
    )


def sample_planning_config() -> PlanningConfig:
    return PlanningConfig(
        model="configured-default",
        granularity=Granularity.STANDARD,
        planning_constraints=[],
        policy=None,
    )


def sample_planning_run() -> PlanningRun:
    return PlanningRun(
        id=PLANNING_RUN_ID,
        spec_revision_id=SPEC_REVISION_ID,
        mode=PlanningMode.TEST,
        status=PlanningStatus.SUCCEEDED,
        config_snapshot=sample_planning_config(),
        attempt_count=1,
        fixture_id="fixture-standard",
        usage=TokenUsage(prompt_tokens=1200, completion_tokens=800, total_tokens=2000),
        error=None,
        proposal=sample_task_proposal(),
        validation_report=sample_validation_report(),
        created_at=SAMPLE_TIME,
        started_at=SAMPLE_TIME,
        finished_at=SAMPLE_TIME,
    )


def sample_failed_run() -> PlanningRun:
    return PlanningRun(
        id=PLANNING_RUN_ID,
        spec_revision_id=SPEC_REVISION_ID,
        mode=PlanningMode.REAL,
        status=PlanningStatus.FAILED,
        config_snapshot=sample_planning_config(),
        attempt_count=3,
        fixture_id=None,
        usage=TokenUsage(prompt_tokens=None, completion_tokens=None, total_tokens=None),
        error=RunError(
            code=RunFailureCode.MODEL_TRUNCATED,
            message="模型输出被截断，修复预算已耗尽",
            retryable=False,
        ),
        proposal=None,
        validation_report=None,
        created_at=SAMPLE_TIME,
        started_at=SAMPLE_TIME,
        finished_at=SAMPLE_TIME,
    )


def sample_plan_revision() -> PlanRevision:
    derivation = sample_derivation()
    tasks = sample_tasks()
    payload = {
        "spec_revision_id": str(SPEC_REVISION_ID),
        "policy_snapshot": None,
        "tasks": [task.model_dump(mode="json", by_alias=True) for task in tasks],
        "edges": [edge.model_dump(mode="json") for edge in derivation.edges],
        "confirmed_assumption_ids": ["A-01"],
        "origin_mode": OriginMode.TEST.value,
        "source": PlanSource.TEST.value,
    }
    return PlanRevision(
        id=PLAN_REVISION_ID,
        plan_id=PLAN_ID,
        revision=1,
        spec_revision_id=SPEC_REVISION_ID,
        planning_run_id=PLANNING_RUN_ID,
        parent_revision_id=None,
        policy_snapshot=None,
        source=PlanSource.TEST,
        origin_mode=OriginMode.TEST,
        confirmed_assumption_ids=["A-01"],
        tasks=tasks,
        edges=derivation.edges,
        execution_stages=derivation.execution_stages,
        parallel_batches=derivation.parallel_batches,
        ordered_task_ids=derivation.ordered_task_ids,
        validation_report=derivation.validation_report,
        hash=sha256_hex(payload),
        created_at=SAMPLE_TIME,
    )


def sample_layout() -> Layout:
    return Layout(
        plan_revision_id=PLAN_REVISION_ID,
        revision=0,
        positions={
            "T-01": Position(x=0, y=0),
            "T-02": Position(x=320, y=0),
            "T-03": Position(x=640, y=0),
            "T-04": Position(x=640, y=120),
            "T-05": Position(x=960, y=60),
        },
        notes=[CanvasNote(id="N-01", text="同层任务可并行，坐标不参与执行顺序", x=0, y=240)],
        viewport=Viewport(x=0, y=0, zoom=1),
    )


def sample_error_envelope() -> ErrorEnvelope:
    return ErrorEnvelope(
        error=ApiError(
            code=ErrorCode.VALIDATION_FAILED,
            message="规格内容不合法",
            issues=[
                Issue(
                    code=IssueCode.SPEC_REQUIRED,
                    severity=IssueSeverity.ERROR,
                    path="/requirements/0/acceptance_criteria",
                    message="需求 R-01 缺少验收条件",
                    task_ids=[],
                    edges=[],
                    suggestion="为 R-01 补充至少一条可验证的验收条件",
                )
            ],
            request_id=REQUEST_ID,
        )
    )


FIXTURES: Final[dict[str, TaskProposal]] = {
    "fixture-standard": sample_task_proposal(),
    "fixture-blocked": sample_blocked_proposal(),
}


def fixture_json(*, sort_keys: bool = False) -> dict[str, str]:
    """用于生成 tech/examples 的文件内容。"""
    payloads = {
        "design-spec": sample_design_spec(),
        "task-proposal": sample_task_proposal(),
        "task-proposal-blocked": sample_blocked_proposal(),
        "planning-run-succeeded": sample_planning_run(),
        "planning-run-failed": sample_failed_run(),
        "plan-derivation": sample_derivation(),
        "plan-revision": sample_plan_revision(),
        "layout": sample_layout(),
        "error-envelope": sample_error_envelope(),
    }
    return {
        name: json.dumps(
            model.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            indent=2,
            sort_keys=sort_keys,
        )
        + "\n"
        for name, model in payloads.items()
    }


__all__ = [
    "FIXTURES",
    "PLANNING_RUN_ID",
    "PLAN_ID",
    "PLAN_REVISION_ID",
    "PROJECT_ID",
    "REQUEST_ID",
    "SAMPLE_TIME",
    "SPEC_ID",
    "SPEC_REVISION_ID",
    "canonical_json",
    "fixture_json",
    "sample_blocked_proposal",
    "sample_derivation",
    "sample_design_spec",
    "sample_error_envelope",
    "sample_failed_run",
    "sample_layout",
    "sample_plan_revision",
    "sample_planning_config",
    "sample_planning_run",
    "sample_task_proposal",
    "sample_tasks",
    "sample_validation_report",
]

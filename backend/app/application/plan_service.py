"""计划保存用例（T07 核心）：校验、来源推导、hash、版本 CAS、落库。

不变量：
- PlanRevision 不可变；durability 由 CAS 与 UNIQUE(plan_id,revision) 保护。
- 服务端重算全部派生字段；客户端提交的 validity/batches/source 一律忽略。
- TEST 来源不会被人工编辑洗掉：source 变 MANUAL 时 origin_mode 仍为 TEST。
- 结构与图校验直接调用 T05 编排器，本层不做第二套算法。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from flowstudio_contracts import (
    AssumptionImpact,
    IssueCode,
    Layout,
    OriginMode,
    PlanningConfig,
    PlanningMode,
    PlanningPolicy,
    PlanningStatus,
    PlanSource,
    Task,
    TaskProposal,
    sha256_hex,
)
from flowstudio_contracts.api import SavePlanRequest, SavePlanResponse, SavePlanRevisionRequest
from flowstudio_contracts.workflow import PlanDerivation
from flowstudio_orchestration import build_plan

from ..errors import make_issue, not_found, revision_conflict, source_mismatch, validation_failed
from ..persistence import repos


@dataclass
class PreparedPlan:
    tasks: list[Task]
    build: PlanDerivation
    source: PlanSource
    origin_mode: OriginMode
    planning_run_id: str | None
    content_hash: str


def _canonical_tasks(tasks: list[Task]) -> list[dict]:
    return sorted(
        (task.model_dump(mode="json", by_alias=True) for task in tasks),
        key=lambda item: item["task_id"],
    )


def _same_tasks(left: list[Task], right: list[Task]) -> bool:
    return _canonical_tasks(left) == _canonical_tasks(right)


def plan_hash(
    *,
    spec_revision_id: str,
    tasks: list[Task],
    policy: PlanningPolicy | None,
    source: str,
    origin_mode: str,
    confirmed_assumption_ids: list[str],
) -> str:
    """计划 hash：含规格引用、任务、约束快照、来源与确认假设；排除 ID/时间/layout。"""
    return sha256_hex(
        {
            "spec_revision_id": spec_revision_id,
            "tasks": _canonical_tasks(tasks),
            "policy": policy.model_dump(mode="json", by_alias=True) if policy is not None else None,
            "source": str(source),
            "origin_mode": str(origin_mode),
            "confirmed_assumption_ids": sorted(confirmed_assumption_ids),
        }
    )


def _check_assumptions(tasks: list[Task], confirmed: list[str]) -> None:
    seen: dict[str, AssumptionImpact] = {}
    for task in tasks:
        for assumption in task.assumptions:
            if assumption.id in seen:
                raise validation_failed(
                    "假设 ID 在同一计划内必须唯一",
                    [
                        make_issue(
                            IssueCode.DUPLICATE_ID,
                            "/tasks",
                            f"假设 ID {assumption.id} 重复",
                            "为不同假设使用唯一 ID",
                        )
                    ],
                )
            seen[assumption.id] = assumption.impact

    critical = sorted(key for key, impact in seen.items() if impact is AssumptionImpact.CRITICAL)
    if critical:
        raise validation_failed(
            "存在关键假设，必须先补充规格再形成正式计划",
            [
                make_issue(
                    IssueCode.CRITICAL_ASSUMPTION,
                    "/tasks",
                    "关键假设未解决：" + ", ".join(critical),
                    "补充规格或返回 NEEDS_INPUT 流程",
                )
            ],
        )

    low = {key for key, impact in seen.items() if impact is AssumptionImpact.LOW}
    supplied = set(confirmed)
    if supplied != low:
        missing = sorted(low - supplied)
        extra = sorted(supplied - low)
        detail = []
        if missing:
            detail.append("未确认：" + ", ".join(missing))
        if extra:
            detail.append("多余：" + ", ".join(extra))
        raise validation_failed(
            "确认的假设必须与当前候选 low 假设集合精确对应",
            [
                make_issue(
                    IssueCode.UNCONFIRMED_ASSUMPTION,
                    "/confirmed_assumption_ids",
                    "；".join(detail) or "假设集合不一致",
                    "显示假设并逐项确认后再保存",
                )
            ],
        )


def _check_layout(layout: Layout, task_ids: set[str]) -> None:
    unknown = sorted(set(layout.positions) - task_ids)
    if unknown:
        raise validation_failed(
            "布局引用了不存在的任务",
            [
                make_issue(
                    IssueCode.MISSING_INPUT,
                    "/layout/positions",
                    "未知 task_id：" + ", ".join(unknown),
                    "只提交该计划内的 task_id",
                )
            ],
        )


def prepare_plan(
    session: Session, *, project_id: str, request: SavePlanRequest
) -> PreparedPlan:
    spec_revision_id = str(request.spec_revision_id)
    spec_revision, spec_row = repos.get_spec_revision(session, spec_revision_id)
    if spec_row.project_id != project_id:
        raise validation_failed(
            "规格版本不属于该项目",
            [
                make_issue(
                    IssueCode.SOURCE_MISMATCH,
                    "/spec_revision_id",
                    "跨项目引用被拒绝",
                    "改用该项目下的规格版本",
                )
            ],
        )

    planning_run_id: str | None = None
    source = PlanSource.MANUAL
    origin_mode = OriginMode.NONE

    if request.planning_run_id is not None:
        run = repos.get_planning_run_row(session, str(request.planning_run_id))
        if run.status != PlanningStatus.SUCCEEDED.value:
            raise source_mismatch(f"规划请求状态为 {run.status}，只有 SUCCEEDED 才能作为来源")
        if run.spec_revision_id != spec_revision_id:
            raise source_mismatch("planning_run 对应的规格版本与请求不一致")
        _, run_spec_row = repos.get_spec_revision(session, run.spec_revision_id)
        if run_spec_row.project_id != project_id:
            raise source_mismatch("planning_run 对应的项目与请求不一致")

        run_config = PlanningConfig.model_validate(repos.load(run.config_json))
        run_policy = (
            run_config.policy.model_dump(mode="json", by_alias=True)
            if run_config.policy
            else None
        )
        request_policy = (
            request.policy.model_dump(mode="json", by_alias=True) if request.policy else None
        )
        if run_policy != request_policy:
            raise source_mismatch("规划参数（policy）与规划请求不一致")

        proposal = TaskProposal.model_validate(repos.load(run.proposal_json))
        unchanged = _same_tasks(proposal.tasks, request.tasks)
        if PlanningMode(run.mode) is PlanningMode.REAL:
            source = PlanSource.AI if unchanged else PlanSource.MANUAL
            origin_mode = OriginMode.REAL
        else:
            source = PlanSource.TEST if unchanged else PlanSource.MANUAL
            origin_mode = OriginMode.TEST
        planning_run_id = run.id

    _check_assumptions(request.tasks, request.confirmed_assumption_ids)

    build = build_plan(request.tasks, spec_revision.content, request.policy)
    if not build.validation_report.valid:
        raise validation_failed(
            "计划未通过结构与图校验",
            build.validation_report.errors,
        )

    if request.layout is not None:
        _check_layout(request.layout, {task.task_id for task in request.tasks})

    content_hash = plan_hash(
        spec_revision_id=spec_revision_id,
        tasks=request.tasks,
        policy=request.policy,
        source=source.value,
        origin_mode=origin_mode.value,
        confirmed_assumption_ids=request.confirmed_assumption_ids,
    )
    return PreparedPlan(
        tasks=list(request.tasks),
        build=build,
        source=source,
        origin_mode=origin_mode,
        planning_run_id=planning_run_id,
        content_hash=content_hash,
    )


def _insert(
    session: Session,
    *,
    plan,  # noqa: ANN001 - PlanRow
    revision: int,
    request: SavePlanRequest,
    prepared: PreparedPlan,
    parent_revision_id: str | None,
) -> "PlanRevision":  # noqa: F821 - 契约模型
    return repos.insert_plan_revision(
        session,
        plan=plan,
        revision=revision,
        spec_revision_id=str(request.spec_revision_id),
        planning_run_id=prepared.planning_run_id,
        parent_revision_id=parent_revision_id,
        policy=request.policy,
        source=prepared.source,
        origin_mode=prepared.origin_mode,
        confirmed_assumption_ids=request.confirmed_assumption_ids,
        content_hash=prepared.content_hash,
        tasks=prepared.tasks,
        edges=[(edge.source, edge.target) for edge in prepared.build.edges],
        stages=prepared.build.execution_stages,
        batches=prepared.build.parallel_batches,
        ordered_task_ids=prepared.build.ordered_task_ids,
        report=prepared.build.validation_report,
        layout=request.layout,
    )


def save_new_plan(session: Session, project_id: str, request: SavePlanRequest) -> SavePlanResponse:
    prepared = prepare_plan(session, project_id=project_id, request=request)
    plan = repos.create_plan_row(session, project_id)
    revision = repos.bump_plan_head(session, plan, 0)
    model = _insert(
        session,
        plan=plan,
        revision=revision,
        request=request,
        prepared=prepared,
        parent_revision_id=None,
    )
    return SavePlanResponse(plan_id=plan.id, revision=model)


def append_plan_revision(
    session: Session, plan_id: str, request: SavePlanRevisionRequest
) -> "PlanRevision":  # noqa: F821 - 契约模型
    plan = repos.get_plan_row(session, plan_id)
    if request.expected_revision != plan.latest_revision:
        raise revision_conflict(plan.latest_revision)

    parent_revision_id = (
        str(request.parent_revision_id) if request.parent_revision_id is not None else None
    )
    if parent_revision_id is not None:
        parent = repos.get_plan_revision_row(session, parent_revision_id)
        if parent.plan_id != plan.id:
            raise validation_failed(
                "parent_revision_id 不属于该计划",
                [
                    make_issue(
                        IssueCode.SOURCE_MISMATCH,
                        "/parent_revision_id",
                        "父版本必须属于同一计划",
                        "改用该计划内的版本 ID",
                    )
                ],
            )

    prepared = prepare_plan(session, project_id=plan.project_id, request=request)
    revision = repos.bump_plan_head(session, plan, request.expected_revision)
    return _insert(
        session,
        plan=plan,
        revision=revision,
        request=request,
        prepared=prepared,
        parent_revision_id=parent_revision_id,
    )


def get_revision_or_404(session: Session, revision_id: str) -> "PlanRevision":  # noqa: F821
    row = repos.get_plan_revision_row(session, revision_id)
    return repos.hydrate_plan_revision(session, row)


__all__ = [
    "PreparedPlan",
    "plan_hash",
    "prepare_plan",
    "save_new_plan",
    "append_plan_revision",
    "get_revision_or_404",
    "not_found",
]

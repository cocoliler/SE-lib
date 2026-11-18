"""仓储层：项目、规格、规划请求、计划版本、布局、命令幂等。

所有写操作都在调用方事务内完成；冲突（CAS 失败）抛 409，缺记录抛 404。
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from flowstudio_contracts import (
    DesignSpecContent,
    Layout,
    OriginMode,
    PlanningConfig,
    PlanningMode,
    PlanningPolicy,
    PlanningRun,
    PlanningStatus,
    PlanRevision,
    PlanSource,
    Project,
    RULES_VERSION,
    RunError,
    RunFailureCode,
    SpecRevision,
    Task,
    TaskProposal,
    TokenUsage,
    ValidationReport,
)
from flowstudio_contracts.api import LayoutWriteRequest
from flowstudio_contracts.codes import RETRYABLE_RUN_FAILURES
from flowstudio_contracts.workflow import (
    CanvasNote,
    ExecutionStage,
    PlanRevisionSummary,
    Position,
    Viewport,
)

from ..errors import not_found, revision_conflict
from ..ids import decode_cursor, encode_cursor, new_id, to_iso
from ..providers.fixtures import normalize_fixture_proposal
from .tables import (
    CommandRow,
    LayoutRow,
    PlanningAttemptRow,
    PlanningRunRow,
    PlanDerivationRow,
    PlanRevisionRow,
    PlanRow,
    ProjectRow,
    SpecRevisionRow,
    SpecRow,
    TaskDependencyRow,
    TaskDetailRow,
    TaskRow,
)


def dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load(raw: str | None, default: Any = None) -> Any:
    if raw is None:
        return default
    return json.loads(raw)


# --------------------------------------------------------------------------- projects


def create_project(session: Session, name: str) -> Project:
    row = ProjectRow(id=new_id(), name=name, archived_at=None, created_at=to_iso())
    session.add(row)
    session.flush()
    return Project(id=row.id, name=row.name, archived_at=row.archived_at, created_at=row.created_at)


def get_project(session: Session, project_id: str) -> Project:
    row = session.get(ProjectRow, project_id)
    if row is None:
        raise not_found("项目不存在")
    return Project(id=row.id, name=row.name, archived_at=row.archived_at, created_at=row.created_at)


def list_projects(
    session: Session, limit: int, cursor: str | None
) -> tuple[list[Project], str | None]:
    statement = select(ProjectRow).order_by(ProjectRow.created_at.desc(), ProjectRow.id.desc())
    statement = _apply_cursor(statement, cursor, ProjectRow)
    rows = list(session.scalars(statement.limit(limit + 1)))
    items, next_cursor = _paginate(rows, limit, lambda row: (row.created_at, row.id))
    return (
        [
            Project(id=row.id, name=row.name, archived_at=row.archived_at, created_at=row.created_at)
            for row in items
        ],
        next_cursor,
    )


# --------------------------------------------------------------------------- specs


def _spec_row_for_project(session: Session, project_id: str, *, create: bool) -> SpecRow:
    project = session.get(ProjectRow, project_id)
    if project is None:
        raise not_found("项目不存在")
    spec = session.scalar(select(SpecRow).where(SpecRow.project_id == project_id))
    if spec is None:
        if not create:
            raise not_found("项目还没有规格")
        spec = SpecRow(id=new_id(), project_id=project_id, latest_revision=0)
        session.add(spec)
        session.flush()
    return spec


def create_spec_revision(
    session: Session,
    project_id: str,
    expected_revision: int,
    content: DesignSpecContent,
    content_hash: str,
) -> SpecRevision:
    spec = _spec_row_for_project(session, project_id, create=(expected_revision == 0))
    if expected_revision != spec.latest_revision:
        raise revision_conflict(spec.latest_revision)

    result = session.execute(
        update(SpecRow)
        .where(SpecRow.id == spec.id, SpecRow.latest_revision == expected_revision)
        .values(latest_revision=expected_revision + 1)
    )
    if result.rowcount != 1:  # pragma: no cover - 并发保护
        session.refresh(spec)
        raise revision_conflict(spec.latest_revision)

    row = SpecRevisionRow(
        id=new_id(),
        spec_id=spec.id,
        revision=expected_revision + 1,
        content_json=dump(content.model_dump(mode="json", by_alias=True)),
        hash=content_hash,
        created_at=to_iso(),
    )
    session.add(row)
    session.flush()
    session.refresh(spec)
    return _spec_revision_model(row, content)


def _spec_revision_model(row: SpecRevisionRow, content: DesignSpecContent | None = None) -> SpecRevision:
    payload = content or DesignSpecContent.model_validate(load(row.content_json))
    return SpecRevision(
        id=row.id,
        spec_id=row.spec_id,
        revision=row.revision,
        content=payload,
        hash=row.hash,
        created_at=row.created_at,
    )


def get_spec_revision(session: Session, revision_id: str) -> tuple[SpecRevision, SpecRow]:
    row = session.get(SpecRevisionRow, revision_id)
    if row is None:
        raise not_found("规格版本不存在")
    spec = session.get(SpecRow, row.spec_id)
    assert spec is not None  # FK 保证
    return _spec_revision_model(row), spec


def get_spec_revision_content(session: Session, revision_id: str) -> DesignSpecContent:
    revision, _ = get_spec_revision(session, revision_id)
    return revision.content


def has_spec(session: Session, project_id: str) -> bool:
    return session.scalar(select(SpecRow).where(SpecRow.project_id == project_id)) is not None


def get_latest_spec_revision(session: Session, project_id: str) -> SpecRevision | None:
    spec = session.scalar(select(SpecRow).where(SpecRow.project_id == project_id))
    if spec is None or spec.latest_revision == 0:
        return None
    row = session.scalar(
        select(SpecRevisionRow)
        .where(SpecRevisionRow.spec_id == spec.id, SpecRevisionRow.revision == spec.latest_revision)
    )
    return _spec_revision_model(row) if row is not None else None


def list_spec_revisions(
    session: Session, project_id: str, limit: int, cursor: str | None
) -> tuple[list[SpecRevision], str | None]:
    spec = _spec_row_for_project(session, project_id, create=False)
    statement = (
        select(SpecRevisionRow)
        .where(SpecRevisionRow.spec_id == spec.id)
        .order_by(SpecRevisionRow.revision.desc(), SpecRevisionRow.id.desc())
    )
    statement = _apply_revision_cursor(statement, cursor, SpecRevisionRow)
    rows = list(session.scalars(statement.limit(limit + 1)))
    items, next_cursor = _paginate(rows, limit, lambda row: (str(row.revision), row.id))
    return ([_spec_revision_model(row) for row in items], next_cursor)


# --------------------------------------------------------------------------- planning runs


def create_planning_run(
    session: Session,
    spec_revision_id: str,
    mode: PlanningMode,
    config: PlanningConfig,
    fixture_id: str | None = None,
) -> PlanningRunRow:
    row = PlanningRunRow(
        id=new_id(),
        spec_revision_id=spec_revision_id,
        status=PlanningStatus.QUEUED.value,
        mode=mode.value,
        config_json=dump(config.model_dump(mode="json", by_alias=True)),
        fixture_id=fixture_id,
        attempt_count=0,
        created_at=to_iso(),
    )
    session.add(row)
    session.flush()
    return row


def get_planning_run_row(session: Session, run_id: str) -> PlanningRunRow:
    row = session.get(PlanningRunRow, run_id)
    if row is None:
        raise not_found("规划请求不存在")
    return row


def _run_error(raw: dict[str, Any]) -> RunError:
    code = RunFailureCode(raw["code"])
    return RunError(
        code=code,
        message=raw["message"],
        provider_request_id=raw.get("provider_request_id"),
        retryable=code in RETRYABLE_RUN_FAILURES,
    )


def planning_run_model(row: PlanningRunRow) -> PlanningRun:
    mode = PlanningMode(row.mode)
    status = PlanningStatus(row.status)
    proposal = TaskProposal.model_validate(load(row.proposal_json)) if row.proposal_json else None
    error = _run_error(load(row.error_json)) if row.error_json else None
    # 兼容旧版 TEST 已落库的 critical-only 记录；轮询不回写历史数据。
    if (
        mode is PlanningMode.TEST
        and status is PlanningStatus.NEEDS_INPUT
        and proposal is not None
        and not proposal.blocking_questions
        and proposal.critical_assumption_ids
    ):
        proposal, error = normalize_fixture_proposal(proposal)
        if error is not None:
            status = PlanningStatus.FAILED
    return PlanningRun(
        id=row.id,
        spec_revision_id=row.spec_revision_id,
        mode=mode,
        status=status,
        config_snapshot=PlanningConfig.model_validate(load(row.config_json)),
        attempt_count=row.attempt_count,
        fixture_id=row.fixture_id,
        usage=TokenUsage.model_validate(load(row.usage_json)) if row.usage_json else None,
        error=error,
        proposal=proposal,
        validation_report=ValidationReport.model_validate(load(row.report_json))
        if row.report_json
        else None,
        created_at=row.created_at,
    )


def mark_run_running(session: Session, run_id: str) -> bool:
    result = session.execute(
        update(PlanningRunRow)
        .where(
            PlanningRunRow.id == run_id,
            PlanningRunRow.status == PlanningStatus.QUEUED.value,
        )
        .values(status=PlanningStatus.RUNNING.value)
    )
    return result.rowcount == 1


def finish_run(
    session: Session,
    run_id: str,
    *,
    status: PlanningStatus,
    proposal: TaskProposal | None,
    report: ValidationReport | None,
    error: RunError | None,
    usage: TokenUsage | None,
    attempt_count: int,
) -> None:
    session.execute(
        update(PlanningRunRow)
        .where(PlanningRunRow.id == run_id)
        .values(
            status=status.value,
            proposal_json=dump(proposal.model_dump(mode="json", by_alias=True))
            if proposal is not None
            else None,
            report_json=dump(report.model_dump(mode="json"))
            if report is not None
            else None,
            error_json=dump(error.model_dump(mode="json")) if error is not None else None,
            usage_json=dump(usage.model_dump(mode="json")) if usage is not None else None,
            attempt_count=attempt_count,
        )
    )


def add_attempt(
    session: Session,
    *,
    run_id: str,
    attempt_no: int,
    request_hash: str,
    response: dict[str, Any] | None,
    usage: dict[str, Any] | None,
    error: dict[str, Any] | None,
) -> None:
    session.add(
        PlanningAttemptRow(
            planning_run_id=run_id,
            attempt_no=attempt_no,
            request_hash=request_hash,
            response_json=dump(response) if response is not None else None,
            usage_json=dump(usage) if usage is not None else None,
            error_json=dump(error) if error is not None else None,
            created_at=to_iso(),
            finished_at=to_iso(),
        )
    )
    session.flush()


def count_attempts(session: Session, run_id: str) -> int:
    rows = session.scalars(
        select(PlanningAttemptRow).where(PlanningAttemptRow.planning_run_id == run_id)
    )
    return len(list(rows))


# --------------------------------------------------------------------------- plans


def create_plan_row(session: Session, project_id: str) -> PlanRow:
    if session.get(ProjectRow, project_id) is None:
        raise not_found("项目不存在")
    row = PlanRow(id=new_id(), project_id=project_id, latest_revision=0)
    session.add(row)
    session.flush()
    return row


def get_plan_row(session: Session, plan_id: str) -> PlanRow:
    row = session.get(PlanRow, plan_id)
    if row is None:
        raise not_found("计划不存在")
    return row


def bump_plan_head(session: Session, plan: PlanRow, expected_revision: int) -> int:
    if plan.latest_revision != expected_revision:
        raise revision_conflict(plan.latest_revision)
    result = session.execute(
        update(PlanRow)
        .where(PlanRow.id == plan.id, PlanRow.latest_revision == expected_revision)
        .values(latest_revision=expected_revision + 1)
    )
    if result.rowcount != 1:  # pragma: no cover - 并发保护
        session.refresh(plan)
        raise revision_conflict(plan.latest_revision)
    session.refresh(plan)
    return plan.latest_revision


def get_plan_revision_row(session: Session, revision_id: str) -> PlanRevisionRow:
    row = session.get(PlanRevisionRow, revision_id)
    if row is None:
        raise not_found("计划版本不存在")
    return row


def insert_plan_revision(
    session: Session,
    *,
    plan: PlanRow,
    revision: int,
    spec_revision_id: str,
    planning_run_id: str | None,
    parent_revision_id: str | None,
    policy: PlanningPolicy | None,
    source: PlanSource,
    origin_mode: OriginMode,
    confirmed_assumption_ids: Iterable[str],
    content_hash: str,
    tasks: list[Task],
    edges: list[tuple[str, str]],
    stages: list[ExecutionStage],
    batches: list[list[str]],
    ordered_task_ids: list[str],
    report: ValidationReport,
    layout: Layout | None,
) -> PlanRevision:
    revision_id = new_id()
    created_at = to_iso()
    session.add(
        PlanRevisionRow(
            id=revision_id,
            plan_id=plan.id,
            revision=revision,
            spec_revision_id=spec_revision_id,
            planning_run_id=planning_run_id,
            parent_revision_id=parent_revision_id,
            policy_json=dump(policy.model_dump(mode="json", by_alias=True)) if policy else None,
            source=source.value,
            origin_mode=origin_mode.value,
            confirmed_assumption_ids_json=dump(sorted(confirmed_assumption_ids)),
            hash=content_hash,
            created_at=created_at,
        )
    )
    session.flush()

    for task in tasks:
        session.add(
            TaskRow(
                revision_id=revision_id,
                task_id=task.task_id,
                name=task.name,
                description=task.description,
                category=task.category,
                stage=task.stage,
                priority=task.priority,
                assigned_role=task.assigned_role,
                rationale=task.rationale,
                effort_json=dump(task.estimated_effort.model_dump(mode="json"))
                if task.estimated_effort
                else None,
            )
        )

    # 先落任务行，保证详情/依赖表的复合外键有父行（SQLite FK 立即检查）
    session.flush()

    for task in tasks:
        session.add(
            TaskDetailRow(
                revision_id=revision_id,
                task_id=task.task_id,
                inputs_json=dump([item.model_dump(mode="json") for item in task.inputs]),
                deliverables_json=dump(
                    [item.model_dump(mode="json") for item in task.deliverables]
                ),
                acceptance_json=dump(list(task.acceptance_criteria)),
                requirement_ids_json=dump(list(task.source_requirement_ids)),
                assumptions_json=dump([item.model_dump(mode="json") for item in task.assumptions]),
            )
        )

    session.flush()

    for source_id, target_id in edges:
        session.add(
            TaskDependencyRow(
                revision_id=revision_id, source_task_id=source_id, target_task_id=target_id
            )
        )

    session.add(
        PlanDerivationRow(
            revision_id=revision_id,
            stages_json=dump([stage.model_dump(mode="json") for stage in stages]),
            batches_json=dump(batches),
            order_json=dump(ordered_task_ids),
            report_json=dump(report.model_dump(mode="json")),
            rules_version=report.rules_version,
        )
    )

    session.add(
        LayoutRow(
            plan_revision_id=revision_id,
            revision=1 if layout is not None else 0,
            positions_json=dump(
                {key: value.model_dump(mode="json") for key, value in (layout.positions.items() if layout else [])}
            ),
            notes_json=dump([note.model_dump(mode="json") for note in layout.notes] if layout else []),
            viewport_json=dump(
                (layout.viewport if layout is not None else _default_viewport()).model_dump(mode="json")
            ),
        )
    )
    session.flush()

    return hydrate_plan_revision(
        session,
        get_plan_revision_row(session, revision_id),
    )


def hydrate_plan_revision(session: Session, row: PlanRevisionRow) -> PlanRevision:
    task_rows = list(
        session.scalars(
            select(TaskRow)
            .where(TaskRow.revision_id == row.id)
            .order_by(TaskRow.task_id)
        )
    )
    detail_rows = {
        detail.task_id: detail
        for detail in session.scalars(
            select(TaskDetailRow).where(TaskDetailRow.revision_id == row.id)
        )
    }
    dependency_rows = list(
        session.scalars(
            select(TaskDependencyRow).where(TaskDependencyRow.revision_id == row.id)
        )
    )
    incoming: dict[str, list[str]] = {}
    for dependency in dependency_rows:
        incoming.setdefault(dependency.target_task_id, []).append(dependency.source_task_id)

    tasks: list[Task] = []
    for task_row in task_rows:
        detail = detail_rows[task_row.task_id]
        tasks.append(
            Task.model_validate(
                {
                    "task_id": task_row.task_id,
                    "name": task_row.name,
                    "description": task_row.description,
                    "category": task_row.category,
                    "stage": task_row.stage,
                    "priority": task_row.priority,
                    "assigned_role": task_row.assigned_role,
                    "dependencies": sorted(incoming.get(task_row.task_id, [])),
                    "inputs": load(detail.inputs_json, []),
                    "deliverables": load(detail.deliverables_json, []),
                    "acceptance_criteria": load(detail.acceptance_json, []),
                    "source_requirement_ids": load(detail.requirement_ids_json, []),
                    "rationale": task_row.rationale,
                    "assumptions": load(detail.assumptions_json, []),
                    "estimated_effort": load(task_row.effort_json)
                    if task_row.effort_json
                    else None,
                }
            )
        )

    derivation = session.get(PlanDerivationRow, row.id)
    assert derivation is not None  # 每个版本落库时同步写入派生结果
    report = ValidationReport.model_validate(load(derivation.report_json))

    return PlanRevision(
        id=row.id,
        plan_id=row.plan_id,
        revision=row.revision,
        spec_revision_id=row.spec_revision_id,
        planning_run_id=row.planning_run_id,
        parent_revision_id=row.parent_revision_id,
        policy_snapshot=PlanningPolicy.model_validate(load(row.policy_json))
        if row.policy_json
        else None,
        source=PlanSource(row.source),
        origin_mode=OriginMode(row.origin_mode),
        confirmed_assumption_ids=load(row.confirmed_assumption_ids_json, []),
        tasks=tasks,
        edges=[
            {"source": dependency.source_task_id, "target": dependency.target_task_id}
            for dependency in sorted(
                dependency_rows,
                key=lambda item: (item.source_task_id, item.target_task_id),
            )
        ],
        execution_stages=[
            ExecutionStage.model_validate(item) for item in load(derivation.stages_json, [])
        ],
        parallel_batches=load(derivation.batches_json, []),
        ordered_task_ids=load(derivation.order_json, []),
        validation_report=report,
        hash=row.hash,
        created_at=row.created_at,
    )


def list_plan_revisions(
    session: Session, plan_id: str, limit: int, cursor: str | None
) -> tuple[list[PlanRevisionSummary], str | None]:
    get_plan_row(session, plan_id)
    statement = (
        select(PlanRevisionRow)
        .where(PlanRevisionRow.plan_id == plan_id)
        .order_by(PlanRevisionRow.revision.desc(), PlanRevisionRow.id.desc())
    )
    statement = _apply_revision_cursor(statement, cursor, PlanRevisionRow)
    rows = list(session.scalars(statement.limit(limit + 1)))
    items, next_cursor = _paginate(rows, limit, lambda row: (str(row.revision), row.id))
    return (
        [
            PlanRevisionSummary(
                id=row.id,
                plan_id=row.plan_id,
                revision=row.revision,
                spec_revision_id=row.spec_revision_id,
                source=PlanSource(row.source),
                origin_mode=OriginMode(row.origin_mode),
                hash=row.hash,
                created_at=row.created_at,
            )
            for row in items
        ],
        next_cursor,
    )


# --------------------------------------------------------------------------- layout


def _default_viewport() -> Viewport:
    return Viewport(x=0.0, y=0.0, zoom=1.0)


def get_layout(session: Session, revision_id: str) -> Layout:
    row = session.get(LayoutRow, revision_id)
    if row is None:
        get_plan_revision_row(session, revision_id)
        return Layout(
            plan_revision_id=revision_id,
            revision=0,
            positions={},
            notes=[],
            viewport=_default_viewport(),
        )
    return Layout(
        plan_revision_id=row.plan_revision_id,
        revision=row.revision,
        positions={
            key: Position.model_validate(value) for key, value in load(row.positions_json, {}).items()
        },
        notes=[CanvasNote.model_validate(item) for item in load(row.notes_json, [])],
        viewport=Viewport.model_validate(load(row.viewport_json, {})),
    )


def put_layout(
    session: Session, revision_id: str, expected_revision: int, payload: LayoutWriteRequest
) -> Layout:
    get_plan_revision_row(session, revision_id)
    row = session.get(LayoutRow, revision_id)
    if row is None:
        if expected_revision != 0:
            raise revision_conflict(0)
        row = LayoutRow(
            plan_revision_id=revision_id,
            revision=1,
            positions_json=dump(
                {key: value.model_dump(mode="json") for key, value in payload.positions.items()}
            ),
            notes_json=dump([note.model_dump(mode="json") for note in payload.notes]),
            viewport_json=dump(payload.viewport.model_dump(mode="json")),
        )
        session.add(row)
        session.flush()
        return get_layout(session, revision_id)

    if row.revision != expected_revision:
        raise revision_conflict(row.revision)
    result = session.execute(
        update(LayoutRow)
        .where(LayoutRow.plan_revision_id == revision_id, LayoutRow.revision == expected_revision)
        .values(
            revision=expected_revision + 1,
            positions_json=dump(
                {key: value.model_dump(mode="json") for key, value in payload.positions.items()}
            ),
            notes_json=dump([note.model_dump(mode="json") for note in payload.notes]),
            viewport_json=dump(payload.viewport.model_dump(mode="json")),
        )
    )
    if result.rowcount != 1:  # pragma: no cover - 并发保护
        raise revision_conflict(get_layout(session, revision_id).revision)
    return get_layout(session, revision_id)


# --------------------------------------------------------------------------- commands


def get_command(session: Session, scope: str, idempotency_key: str) -> CommandRow | None:
    return session.get(CommandRow, (scope, idempotency_key))


def put_command(
    session: Session,
    scope: str,
    idempotency_key: str,
    request_hash: str,
    status_code: int,
    body: dict[str, Any],
) -> None:
    session.add(
        CommandRow(
            scope=scope,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            result_json=dump({"status": status_code, "body": body}),
            created_at=to_iso(),
        )
    )
    session.flush()


# --------------------------------------------------------------------------- pagination


def _apply_cursor(statement, cursor: str | None, model, order_col=None):  # noqa: ANN001
    if not cursor:
        return statement
    created_at, row_id = decode_cursor(cursor)
    column = order_col if order_col is not None else model.created_at
    return statement.where(
        (column < created_at) | ((column == created_at) & (model.id < row_id))
    )


def _apply_revision_cursor(statement, cursor: str | None, model):  # noqa: ANN001
    """按 revision 倒序的分页游标（revision 是整数，需显式转换）。"""
    if not cursor:
        return statement
    raw, row_id = decode_cursor(cursor)
    revision = int(raw)
    return statement.where(
        (model.revision < revision) | ((model.revision == revision) & (model.id < row_id))
    )


def _paginate(rows: list, limit: int, key):  # noqa: ANN001, ANN201
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = encode_cursor(*key(items[-1])) if has_more and items else None
    return items, next_cursor

"""规划请求：创建（202）、轮询、读取候选任务。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from flowstudio_contracts import PlanningMode, PlanningStatus
from flowstudio_contracts.api import (
    CreatePlanningRunRequest,
    PlanningRunTasksResponse,
)
from flowstudio_contracts.planning import PlanningRun, PlanningRunCreated

from ..errors import queue_full, result_not_ready, validation_failed
from ..persistence import repos
from . import idempotency as idem
from .deps import get_session

router = APIRouter(prefix="/planning-runs", tags=["planning"])


@router.post("", response_model=PlanningRunCreated, status_code=202)
def create_planning_run(
    payload: CreatePlanningRunRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    context = idem.read(request, payload)
    cached = idem.replay(session, context)
    if cached is not None:
        return cached

    spec_revision, _ = repos.get_spec_revision(session, str(payload.spec_revision_id))

    engine = request.app.state.engine
    settings = request.app.state.settings

    if payload.mode is PlanningMode.TEST and payload.fixture_id not in engine.fixtures():
        raise validation_failed(f"fixture {payload.fixture_id} 不存在")

    requested_model = payload.config.model
    if requested_model == "configured-default":
        resolved_model = settings.default_model
    elif requested_model in settings.model_allowlist:
        resolved_model = requested_model
    else:
        raise validation_failed(f"模型不在服务端 allowlist 中：{requested_model}")

    config = payload.config.model_copy(update={"model": resolved_model})

    if not request.app.state.queue.has_capacity():
        raise queue_full()

    run = repos.create_planning_run(
        session,
        str(spec_revision.id),
        payload.mode,
        config,
        payload.fixture_id,
    )
    body = PlanningRunCreated(
        id=run.id,
        status=PlanningStatus.QUEUED,
        poll_url=f"/api/v1/planning-runs/{run.id}",
    ).model_dump(mode="json")
    idem.store(session, context, 202, body)
    session.commit()

    request.app.state.queue.submit(run.id)
    return body


@router.get("/{run_id}", response_model=PlanningRun)
def get_planning_run(run_id: str, session: Session = Depends(get_session)):
    row = repos.get_planning_run_row(session, run_id)
    return repos.planning_run_model(row)


@router.get("/{run_id}/tasks", response_model=PlanningRunTasksResponse)
def get_planning_tasks(run_id: str, session: Session = Depends(get_session)):
    row = repos.get_planning_run_row(session, run_id)
    if row.status != PlanningStatus.SUCCEEDED.value:
        raise result_not_ready(f"规划请求状态为 {row.status}")
    model = repos.planning_run_model(row)
    return PlanningRunTasksResponse(tasks=model.proposal.tasks if model.proposal else [])

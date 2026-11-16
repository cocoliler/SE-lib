"""计划版本：新建、追加修订、历史、布局、导出。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from flowstudio_contracts import IssueCode, Layout, PlanRevision
from flowstudio_contracts.api import (
    LayoutWriteRequest,
    PlanRevisionSummaryPage,
    SavePlanRequest,
    SavePlanResponse,
    SavePlanRevisionRequest,
)
from flowstudio_contracts.workflow import ExportBundle
from ..application import plan_service
from ..errors import make_issue, validation_failed
from ..persistence import repos
from . import idempotency as idem
from .deps import get_session, page_params

router = APIRouter(tags=["plans"])


@router.post("/projects/{project_id}/plans", response_model=SavePlanResponse, status_code=201)
def create_plan(
    project_id: str,
    payload: SavePlanRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    context = idem.read(request, payload)
    cached = idem.replay(session, context)
    if cached is not None:
        return cached

    created = plan_service.save_new_plan(session, project_id, payload)
    body = created.model_dump(mode="json")
    idem.store(session, context, 201, body)
    session.commit()
    return created


@router.post("/plans/{plan_id}/revisions", response_model=PlanRevision, status_code=201)
def append_revision(
    plan_id: str,
    payload: SavePlanRevisionRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    context = idem.read(request, payload)
    cached = idem.replay(session, context)
    if cached is not None:
        return cached

    revision = plan_service.append_plan_revision(session, plan_id, payload)
    body = revision.model_dump(mode="json")
    idem.store(session, context, 201, body)
    session.commit()
    return revision


@router.get("/plans/{plan_id}/revisions", response_model=PlanRevisionSummaryPage)
def list_revisions(
    plan_id: str,
    session: Session = Depends(get_session),
    page: tuple[int, str | None] = Depends(page_params),
):
    limit, cursor = page
    try:
        items, next_cursor = repos.list_plan_revisions(session, plan_id, limit, cursor)
    except ValueError as exc:
        raise validation_failed("cursor 不合法") from exc
    return PlanRevisionSummaryPage(items=items, next_cursor=next_cursor)


@router.get("/plan-revisions/{revision_id}", response_model=PlanRevision)
def get_revision(revision_id: str, session: Session = Depends(get_session)):
    return plan_service.get_revision_or_404(session, revision_id)


@router.get("/plan-revisions/{revision_id}/layout", response_model=Layout)
def get_layout(revision_id: str, session: Session = Depends(get_session)):
    return repos.get_layout(session, revision_id)


@router.put("/plan-revisions/{revision_id}/layout", response_model=Layout)
def put_layout(
    revision_id: str,
    payload: LayoutWriteRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    context = idem.read(request, payload)
    cached = idem.replay(session, context)
    if cached is not None:
        return cached

    revision = plan_service.get_revision_or_404(session, revision_id)
    task_ids = {task.task_id for task in revision.tasks}
    unknown = sorted(set(payload.positions) - task_ids)
    if unknown:
        raise validation_failed(
            "布局引用了不存在的任务",
            [
                make_issue(
                    IssueCode.MISSING_INPUT,
                    "/positions",
                    "未知 task_id：" + ", ".join(unknown),
                    "只提交该计划版本内的 task_id",
                )
            ],
        )

    layout = repos.put_layout(session, revision_id, payload.expected_revision, payload)
    body = layout.model_dump(mode="json")
    idem.store(session, context, 200, body)
    session.commit()
    return layout


@router.get("/plan-revisions/{revision_id}/export")
def export_revision(
    revision_id: str,
    format: str = Query("json", alias="format"),
    session: Session = Depends(get_session),
):
    if format != "json":
        raise validation_failed("目前只支持 format=json")
    revision = plan_service.get_revision_or_404(session, revision_id)
    spec_revision, _ = repos.get_spec_revision(session, str(revision.spec_revision_id))
    layout = repos.get_layout(session, revision_id)
    bundle = ExportBundle(
        schema_version="1.0",
        spec_snapshot=spec_revision.content,
        policy_snapshot=revision.policy_snapshot,
        plan_revision=revision,
        layout=layout,
    )
    filename = f"plan-{revision.plan_id}-r{revision.revision}.json"
    return JSONResponse(
        content=json.loads(bundle.model_dump_json()),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

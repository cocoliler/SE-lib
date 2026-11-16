"""项目资源。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from flowstudio_contracts import Project
from flowstudio_contracts.api import CreateProjectRequest, ProjectPage

from ..errors import validation_failed
from ..persistence import repos
from . import idempotency as idem
from .deps import get_session, page_params

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=Project, status_code=201)
def create_project(
    payload: CreateProjectRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    context = idem.read(request, payload)
    cached = idem.replay(session, context)
    if cached is not None:
        return cached

    project = repos.create_project(session, payload.name)
    body = project.model_dump(mode="json")
    idem.store(session, context, 201, body)
    session.commit()
    return project


@router.get("", response_model=ProjectPage)
def list_projects(
    session: Session = Depends(get_session),
    page: tuple[int, str | None] = Depends(page_params),
):
    limit, cursor = page
    try:
        items, next_cursor = repos.list_projects(session, limit, cursor)
    except ValueError as exc:
        raise validation_failed("cursor 不合法") from exc
    return ProjectPage(items=items, next_cursor=next_cursor)

"""规格：版本保存（CAS）、查询、预览校验。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from flowstudio_contracts import (
    SpecRevision,
    ValidationReport,
    content_hash,
)
from flowstudio_contracts.api import (
    SpecRevisionPage,
    SpecRevisionWriteRequest,
    SpecValidationRequest,
)

from ..domain.spec_validation import validate_spec
from ..errors import validation_failed
from ..persistence import repos
from . import idempotency as idem
from .deps import get_session, page_params

project_router = APIRouter(prefix="/projects", tags=["specs"])
spec_router = APIRouter(prefix="/spec-revisions", tags=["specs"])
validation_router = APIRouter(prefix="/spec-validations", tags=["specs"])


@project_router.post("/{project_id}/spec-revisions", response_model=SpecRevision, status_code=201)
def create_spec_revision(
    project_id: str,
    payload: SpecRevisionWriteRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    context = idem.read(request, payload)
    cached = idem.replay(session, context)
    if cached is not None:
        return cached

    revision = repos.create_spec_revision(
        session,
        project_id,
        payload.expected_revision,
        payload.content,
        content_hash(payload.content),
    )
    body = revision.model_dump(mode="json")
    idem.store(session, context, 201, body)
    session.commit()
    return revision


@project_router.get("/{project_id}/spec-revisions", response_model=SpecRevisionPage)
def list_spec_revisions(
    project_id: str,
    session: Session = Depends(get_session),
    page: tuple[int, str | None] = Depends(page_params),
):
    limit, cursor = page
    repos.get_project(session, project_id)
    if not repos.has_spec(session, project_id):
        return SpecRevisionPage(items=[], next_cursor=None)
    try:
        items, next_cursor = repos.list_spec_revisions(session, project_id, limit, cursor)
    except ValueError as exc:
        raise validation_failed("cursor 不合法") from exc
    return SpecRevisionPage(items=items, next_cursor=next_cursor)


@spec_router.get("/{revision_id}", response_model=SpecRevision)
def get_spec_revision(revision_id: str, session: Session = Depends(get_session)):
    revision, _ = repos.get_spec_revision(session, revision_id)
    return revision


@validation_router.post("", response_model=ValidationReport)
def validate_spec_content(payload: SpecValidationRequest):
    return validate_spec(payload.content)

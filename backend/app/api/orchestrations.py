"""编排与图校验：直接调用 T05 编排器，无效输入仍返回 200 + report.valid=false。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from flowstudio_contracts.api import OrchestrationRequest, WorkflowValidationRequest
from flowstudio_contracts.validation import ValidationReport
from flowstudio_contracts.workflow import PlanDerivation
from flowstudio_orchestration import build_plan, validate_workflow

from ..persistence import repos
from .deps import get_session

router = APIRouter(tags=["orchestration"])


@router.post("/orchestrations", response_model=PlanDerivation)
def orchestrate(payload: OrchestrationRequest, session: Session = Depends(get_session)):
    spec_revision, _ = repos.get_spec_revision(session, str(payload.spec_revision_id))
    return build_plan(payload.tasks, spec_revision.content, payload.policy)


@router.post("/workflow-validations", response_model=ValidationReport)
def validate_workflow_endpoint(
    payload: WorkflowValidationRequest, session: Session = Depends(get_session)
):
    spec_revision, _ = repos.get_spec_revision(session, str(payload.spec_revision_id))
    return validate_workflow(payload.tasks, spec_revision.content, payload.policy)

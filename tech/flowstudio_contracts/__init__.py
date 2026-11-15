"""FlowStudio 统一契约层。

单一事实源：`app/domain/tech/*.py` 的 Pydantic 模型。
派生产物：`tech/schema/*.schema.json`、`tech/openapi.json`、
`frontend/src/api/generated/contracts.ts`，全部由脚本生成，禁止手改。
"""

from .base import StrictModel, canonical_json, content_hash, sha256_hex
from .codes import ERROR_HTTP_STATUS, ErrorCode, IssueCode, RunFailureCode
from .constants import API_PREFIX, PROMPT_VERSION, RULES_VERSION, SCHEMA_VERSION
from .planning import (
    Granularity,
    PlanningConfig,
    PlanningMode,
    PlanningPolicy,
    PlanningRun,
    PlanningStatus,
    RunError,
    TokenUsage,
)
from .spec import DesignSpecContent, Requirement, RequirementKind, RequirementPriority
from .tasks import AssumptionImpact, Task, TaskPriority, TaskProposal
from .validation import Issue, IssueSeverity, TaskEdge, ValidationReport
from .workflow import (
    Layout,
    OriginMode,
    PlanRevision,
    PlanSource,
    Project,
    SpecRevision,
)

__all__ = [
    "API_PREFIX",
    "AssumptionImpact",
    "DesignSpecContent",
    "ERROR_HTTP_STATUS",
    "ErrorCode",
    "Granularity",
    "Issue",
    "IssueCode",
    "IssueSeverity",
    "Layout",
    "OriginMode",
    "PROMPT_VERSION",
    "PlanRevision",
    "PlanSource",
    "PlanningConfig",
    "PlanningMode",
    "PlanningPolicy",
    "PlanningRun",
    "PlanningStatus",
    "Project",
    "RULES_VERSION",
    "Requirement",
    "RequirementKind",
    "RequirementPriority",
    "RunError",
    "RunFailureCode",
    "SCHEMA_VERSION",
    "SpecRevision",
    "StrictModel",
    "Task",
    "TaskEdge",
    "TaskPriority",
    "TaskProposal",
    "TokenUsage",
    "ValidationReport",
    "canonical_json",
    "content_hash",
    "sha256_hex",
]

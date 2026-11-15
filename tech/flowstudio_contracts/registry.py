"""契约清单：哪些模型对外导出为 JSON Schema，哪些进入 OpenAPI/TS。

新增字段只改模型；导出物一律由 `tech/scripts/export_contracts.py` 生成。
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel

from .api import ErrorEnvelope, OPERATIONS
from .planning import PlanningPolicy, PlanningRun, PlanningRunCreated
from .spec import DesignSpecContent
from .tasks import TaskProposal
from .validation import ValidationReport
from .workflow import ExportBundle, Layout, PlanDerivation, PlanRevision, Project, SpecRevision

SCHEMA_EXPORTS: Final[dict[str, type[BaseModel]]] = {
    "design-spec": DesignSpecContent,
    "task-proposal": TaskProposal,
    "planning-policy": PlanningPolicy,
    "planning-run": PlanningRun,
    "planning-run-created": PlanningRunCreated,
    "plan-derivation": PlanDerivation,
    "plan-revision": PlanRevision,
    "spec-revision": SpecRevision,
    "project": Project,
    "layout": Layout,
    "validation-report": ValidationReport,
    "export-bundle": ExportBundle,
    "error-envelope": ErrorEnvelope,
}


def exported_models() -> dict[str, type[BaseModel]]:
    """返回 {文件名: 模型}，按名称排序保证输出稳定。"""
    return dict(sorted(SCHEMA_EXPORTS.items()))


def referenced_models() -> tuple[type[BaseModel], ...]:
    """OpenAPI/TS 需要覆盖的模型：导出清单 + 所有 operation 的请求/响应。"""
    models: dict[str, type[BaseModel]] = dict(SCHEMA_EXPORTS)
    for operation in OPERATIONS:
        for model in (operation.request_model, operation.response_model):
            if model is not None:
                models[model.__name__] = model
    return tuple(models.values())


__all__ = ["SCHEMA_EXPORTS", "exported_models", "referenced_models"]

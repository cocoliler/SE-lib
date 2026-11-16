"""API 路由聚合（统一前缀 /api/v1）。

路由集合必须与 `flowstudio_contracts.api.OPERATIONS` 一一对应，
由 `tools/export_openapi.py` 做漂移检查；不额外注册契约之外的路由。
"""

from __future__ import annotations

from fastapi import APIRouter

from flowstudio_contracts import API_PREFIX

from . import orchestrations, planning, plans, projects, specs

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(projects.router)
api_router.include_router(specs.project_router)
api_router.include_router(specs.spec_router)
api_router.include_router(specs.validation_router)
api_router.include_router(planning.router)
api_router.include_router(orchestrations.router)
api_router.include_router(plans.router)

__all__ = ["api_router"]

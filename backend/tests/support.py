"""测试辅助：导入路径引导与最小合法契约对象构造。

必须先于 `flowstudio_orchestration` 导入本模块，路径引导才会生效：

    import support  # noqa: F401

同时把仓库的 `tech/`（契约层）和 `backend/`（本模块）加入 sys.path，
所以 `python -m unittest discover -s tests -v` 在 backend 目录即可运行。
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _entry in (str(_ROOT / "tech"), str(_BACKEND)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from flowstudio_contracts import (  # noqa: E402  (路径引导之后再导入)
    AssumptionImpact,
    DesignSpecContent,
    Requirement,
    RequirementKind,
    RequirementPriority,
    Task,
    TaskPriority,
)
from flowstudio_contracts.planning import PlanningPolicy, StageEdge  # noqa: E402
from flowstudio_contracts.tasks import (  # noqa: E402
    Deliverable,
    SpecInput,
    TaskAssumption,
    TaskInput,
)


def requirement(
    requirement_id: str,
    priority: RequirementPriority = RequirementPriority.MUST,
) -> Requirement:
    return Requirement(
        id=requirement_id,
        kind=RequirementKind.FUNCTIONAL,
        text=f"实现 {requirement_id}",
        priority=priority,
        acceptance_criteria=[f"{requirement_id} 可被观察验收"],
    )


def spec(*requirements: str | Requirement) -> DesignSpecContent:
    items = [requirement(item) if isinstance(item, str) else item for item in requirements]
    return DesignSpecContent(
        schema_version="1.0",
        product_name="编排测试产品",
        background="仅用于编排单元测试的最小规格。",
        goals=["验证确定性编排"],
        target_users=["开发者"],
        requirements=items or [requirement("R-01")],
        technical_constraints=[],
        development_constraints=[],
        delivery_requirements=["可运行原型"],
        acceptance_criteria=["流程可演示"],
        supplemental_text="",
        confirmed_assumptions=[],
    )


def task(
    task_id: str,
    *,
    stage: str = "build",
    category: str = "build",
    role: str = "developer",
    dependencies: tuple[str, ...] = (),
    requirements: tuple[str, ...] = (),
    deliverables: list[Deliverable] | None = None,
    inputs: tuple[SpecInput | TaskInput, ...] = (),
    assumptions: tuple[TaskAssumption, ...] = (),
    name: str | None = None,
    rationale: str = "依据规格安排",
) -> Task:
    return Task(
        task_id=task_id,
        name=name or f"任务 {task_id}",
        description=f"{task_id} 的描述",
        category=category,
        stage=stage,
        priority=TaskPriority.MEDIUM,
        assigned_role=role,
        dependencies=list(dependencies),
        inputs=list(inputs),
        deliverables=(
            list(deliverables)
            if deliverables is not None
            else [Deliverable(id=f"D-{task_id}", text=f"{task_id} 的交付")]
        ),
        acceptance_criteria=[f"{task_id} 可验收"],
        source_requirement_ids=list(requirements),
        rationale=rationale,
        assumptions=list(assumptions),
        estimated_effort=None,
    )


def unvalidated(task_object: Task, **overrides: object) -> Task:
    """绕过契约校验构造非法 fixture（如重复依赖），用于验证引擎的防御性检查。"""
    return task_object.model_copy(update=overrides)


def task_input(task_id: str, deliverable_id: str) -> TaskInput:
    return TaskInput(kind="task", task_id=task_id, deliverable_id=deliverable_id)


def spec_input(requirement_id: str) -> SpecInput:
    return SpecInput(kind="spec", requirement_id=requirement_id)


def assumption(
    assumption_id: str,
    *,
    impact: AssumptionImpact = AssumptionImpact.LOW,
    text: str | None = None,
) -> TaskAssumption:
    return TaskAssumption(
        id=assumption_id,
        text=text or f"假设 {assumption_id}",
        impact=impact,
    )


def policy(
    *,
    stages: list[str] | None = None,
    roles: list[str] | None = None,
    categories: list[str] | None = None,
    stage_edges: list[StageEdge] | None = None,
    required: tuple[str, ...] = (),
) -> PlanningPolicy:
    return PlanningPolicy(
        schema_version="1.0",
        rules_version="1.0",
        allowed_stages=stages,
        allowed_roles=roles,
        allowed_categories=categories,
        allowed_stage_edges=stage_edges,
        required_categories=list(required),
    )


def stage_edge(from_stage: str, to_stage: str) -> StageEdge:
    return StageEdge.model_validate({"from": from_stage, "to": to_stage})


__all__ = [
    "assumption",
    "policy",
    "requirement",
    "spec",
    "spec_input",
    "stage_edge",
    "task",
    "task_input",
    "unvalidated",
]

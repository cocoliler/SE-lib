"""任务提案契约：PM Agent 的结构化输出，也是人工编辑与保存的同一形状。

本模块只约束"形状与命名"，任务唯一性、依赖存在性、环检测属于编排器的图校验，
不在此重复实现，避免两处规则漂移。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from .base import BodyText, Identifier, LongText, RationaleText, ShortText, StrictModel, duplicates, enum_value
from .constants import (
    MAX_BLOCKING_QUESTIONS,
    MAX_TASK_ASSUMPTIONS,
    MAX_TASK_DELIVERABLES,
    MAX_TASK_DEPENDENCIES,
    MAX_TASK_INPUTS,
    MAX_TASK_REQUIREMENT_REFS,
    MAX_TASKS,
)


class TaskPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AssumptionImpact(StrEnum):
    LOW = "low"
    CRITICAL = "critical"


class Deliverable(StrictModel):
    """任务产出的可引用成果；id 在其所属任务内唯一。"""

    id: Identifier
    text: BodyText


class TaskAssumption(StrictModel):
    """非关键假设随候选显示；critical 假设必须回到补规格流程。"""

    id: Identifier
    text: BodyText
    impact: enum_value(AssumptionImpact)


class SpecInput(StrictModel):
    kind: Literal["spec"]
    requirement_id: Identifier


class TaskInput(StrictModel):
    kind: Literal["task"]
    task_id: Identifier
    deliverable_id: Identifier


InputRef = Annotated[Union[SpecInput, TaskInput], Field(discriminator="kind")]


class EstimatedEffort(StrictModel):
    """工时只能是估算：is_estimate 恒为 true，不表示真实排期承诺。"""

    min_hours: Annotated[float, Field(gt=0)]
    max_hours: Annotated[float, Field(gt=0)]
    basis: BodyText
    is_estimate: Literal[True]

    @model_validator(mode="after")
    def _ordered_range(self) -> EstimatedEffort:
        if self.min_hours > self.max_hours:
            raise ValueError("estimated_effort.min_hours 不能大于 max_hours")
        return self


class Task(StrictModel):
    task_id: Identifier
    name: ShortText
    description: LongText
    category: Identifier
    stage: Identifier
    priority: enum_value(TaskPriority)
    assigned_role: Identifier
    dependencies: Annotated[list[Identifier], Field(max_length=MAX_TASK_DEPENDENCIES)]
    inputs: Annotated[list[InputRef], Field(max_length=MAX_TASK_INPUTS)]
    deliverables: Annotated[list[Deliverable], Field(min_length=1, max_length=MAX_TASK_DELIVERABLES)]
    acceptance_criteria: Annotated[list[BodyText], Field(min_length=1, max_length=MAX_TASK_DELIVERABLES)]
    source_requirement_ids: Annotated[list[Identifier], Field(max_length=MAX_TASK_REQUIREMENT_REFS)]
    rationale: RationaleText
    assumptions: Annotated[list[TaskAssumption], Field(max_length=MAX_TASK_ASSUMPTIONS)]
    estimated_effort: Union[EstimatedEffort, None]

    @model_validator(mode="after")
    def _unique_local_ids(self) -> Task:
        repeated = duplicates(self.dependencies)
        if repeated:
            raise ValueError(f"dependencies 存在重复引用：{sorted(repeated)}")
        repeated = duplicates(item.id for item in self.deliverables)
        if repeated:
            raise ValueError(f"deliverables/id 存在重复：{sorted(repeated)}")
        repeated = duplicates(item.id for item in self.assumptions)
        if repeated:
            raise ValueError(f"assumptions/id 存在重复：{sorted(repeated)}")
        repeated = duplicates(self.source_requirement_ids)
        if repeated:
            raise ValueError(f"source_requirement_ids 存在重复：{sorted(repeated)}")
        return self


class TaskProposal(StrictModel):
    """一次规划的候选任务集；tasks 为空必须伴随 blocking_questions。"""

    schema_version: Literal["1.0"]
    tasks: Annotated[list[Task], Field(max_length=MAX_TASKS)]
    blocking_questions: Annotated[list[BodyText], Field(max_length=MAX_BLOCKING_QUESTIONS)]

    @model_validator(mode="after")
    def _empty_requires_questions(self) -> TaskProposal:
        if not self.tasks and not self.blocking_questions:
            raise ValueError("tasks 为空时必须提供 blocking_questions，不能提交无可执行内容的候选")
        return self

    @property
    def is_blocked(self) -> bool:
        return bool(self.blocking_questions)

    @property
    def critical_assumption_ids(self) -> list[str]:
        return [
            assumption.id
            for task in self.tasks
            for assumption in task.assumptions
            if assumption.impact is AssumptionImpact.CRITICAL
        ]

    @property
    def low_assumption_ids(self) -> list[str]:
        return [
            assumption.id
            for task in self.tasks
            for assumption in task.assumptions
            if assumption.impact is AssumptionImpact.LOW
        ]


__all__ = [
    "AssumptionImpact",
    "Deliverable",
    "EstimatedEffort",
    "InputRef",
    "SpecInput",
    "Task",
    "TaskAssumption",
    "TaskInput",
    "TaskPriority",
    "TaskProposal",
]

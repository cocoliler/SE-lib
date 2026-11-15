"""Design Spec 契约：需求有稳定 ID 与可验收条件，是 PM Agent 的唯一定义输入。"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import BodyText, Identifier, ShortText, StrictModel, enum_value, text
from .constants import (
    MAX_BACKGROUND,
    MAX_CONFIRMED_ASSUMPTIONS,
    MAX_GOALS,
    MAX_PRODUCT_NAME,
    MAX_REQUIREMENT_CRITERIA,
    MAX_REQUIREMENTS,
    MAX_SPEC_CONSTRAINTS,
    MAX_SUPPLEMENTAL_TEXT,
    MAX_TARGET_USERS,
)


class RequirementKind(StrEnum):
    FUNCTIONAL = "functional"
    NONFUNCTIONAL = "nonfunctional"


class RequirementPriority(StrEnum):
    MUST = "must"
    SHOULD = "should"
    COULD = "could"


class Requirement(StrictModel):
    """单条需求；同一 SpecRevision 内 id 唯一，正文可改而 id 不变。"""

    id: Identifier
    kind: enum_value(RequirementKind)
    text: BodyText
    priority: enum_value(RequirementPriority)
    acceptance_criteria: Annotated[list[BodyText], Field(min_length=1, max_length=MAX_REQUIREMENT_CRITERIA)]


class DesignSpecContent(StrictModel):
    """规格内容（不可变 SpecRevision.content）。字段均必填，空数组也需显式给出。"""

    schema_version: Literal["1.0"]
    product_name: text(1, MAX_PRODUCT_NAME)
    background: text(1, MAX_BACKGROUND)
    goals: Annotated[list[ShortText], Field(min_length=1, max_length=MAX_GOALS)]
    target_users: Annotated[list[ShortText], Field(min_length=1, max_length=MAX_TARGET_USERS)]
    requirements: Annotated[list[Requirement], Field(min_length=1, max_length=MAX_REQUIREMENTS)]
    technical_constraints: Annotated[list[ShortText], Field(max_length=MAX_SPEC_CONSTRAINTS)]
    development_constraints: Annotated[list[ShortText], Field(max_length=MAX_SPEC_CONSTRAINTS)]
    delivery_requirements: Annotated[list[ShortText], Field(min_length=1, max_length=MAX_SPEC_CONSTRAINTS)]
    acceptance_criteria: Annotated[list[ShortText], Field(min_length=1, max_length=MAX_SPEC_CONSTRAINTS)]
    supplemental_text: text(0, MAX_SUPPLEMENTAL_TEXT)
    confirmed_assumptions: Annotated[list[ShortText], Field(max_length=MAX_CONFIRMED_ASSUMPTIONS)]

    @model_validator(mode="after")
    def _unique_requirement_ids(self) -> DesignSpecContent:
        seen: dict[str, int] = {}
        for index, requirement in enumerate(self.requirements):
            if requirement.id in seen:
                raise ValueError(
                    f"requirements/{index}/id 重复：{requirement.id!r} 与 requirements/{seen[requirement.id]}/id 相同"
                )
            seen[requirement.id] = index
        return self

    @property
    def requirement_ids(self) -> list[str]:
        return [item.id for item in self.requirements]

    @property
    def must_requirement_ids(self) -> list[str]:
        return [item.id for item in self.requirements if item.priority is RequirementPriority.MUST]


__all__ = ["DesignSpecContent", "Requirement", "RequirementKind", "RequirementPriority"]

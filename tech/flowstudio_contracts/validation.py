"""缺陷与校验报告契约：定位到字段路径，绑定 input_hash 与规则版本。

valid 仅表示 errors 为空；warnings 允许存在。报告只对给定输入有效，
过期报告不能作为保存凭证。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import BodyText, Identifier, RationaleText, Sha256Hex, StrictModel, enum_value
from .codes import IssueCode
from .constants import MAX_ISSUE_REFS


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class TaskEdge(StrictModel):
    """依赖边 source→target，表示 target 必须等待 source。"""

    source: Identifier
    target: Identifier


class Issue(StrictModel):
    """单条缺陷；path 为 JSON Pointer，例如 /tasks/2/dependencies/0。"""

    code: enum_value(IssueCode)
    severity: enum_value(IssueSeverity)
    path: Annotated[str, Field(pattern=r"^(/[^/]*)*$", max_length=200)]
    message: BodyText
    task_ids: Annotated[list[Identifier], Field(max_length=MAX_ISSUE_REFS)]
    edges: Annotated[list[TaskEdge], Field(max_length=MAX_ISSUE_REFS)]
    suggestion: RationaleText

    @model_validator(mode="after")
    def _code_severity(self) -> Issue:
        advisory = {
            IssueCode.POSSIBLE_DUPLICATE,
            IssueCode.ORPHAN,
        }
        if self.code in advisory and self.severity is not IssueSeverity.WARNING:
            raise ValueError(f"{self.code} 只能是 warning，不能作为硬错误")
        if self.code not in advisory and self.severity is not IssueSeverity.ERROR:
            raise ValueError(f"{self.code} 是硬错误，不能降级为 warning")
        return self


class Coverage(StrictModel):
    covered_ids: Annotated[list[Identifier], Field(max_length=MAX_ISSUE_REFS)]
    uncovered_ids: Annotated[list[Identifier], Field(max_length=MAX_ISSUE_REFS)]

    @model_validator(mode="after")
    def _disjoint(self) -> Coverage:
        overlap = set(self.covered_ids) & set(self.uncovered_ids)
        if overlap:
            raise ValueError(f"covered_ids 与 uncovered_ids 重复：{sorted(overlap)}")
        return self


class ValidationReport(StrictModel):
    valid: bool
    errors: list[Issue]
    warnings: list[Issue]
    coverage: Coverage
    rules_version: Literal["1.0"]
    input_hash: Sha256Hex

    @model_validator(mode="after")
    def _consistent(self) -> ValidationReport:
        if self.valid != (not self.errors):
            raise ValueError("valid 必须等于 errors 为空")
        return self


__all__ = [
    "Coverage",
    "Issue",
    "IssueSeverity",
    "TaskEdge",
    "ValidationReport",
]

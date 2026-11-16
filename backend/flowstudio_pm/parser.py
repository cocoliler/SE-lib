"""模型候选的严格结构校验及阻塞问题整理。"""

from __future__ import annotations

import json
import math

from pydantic import TypeAdapter, ValidationError

from flowstudio_contracts import AssumptionImpact, RunFailureCode, TaskProposal
from flowstudio_contracts.base import BodyText
from flowstudio_contracts.constants import MAX_BLOCKING_QUESTIONS, MAX_BODY_BYTES

from .types import ProviderResponse


class ProposalError(Exception):
    """结构问题只保留本地语句和安全的 JSON Pointer。"""

    def __init__(self, code: RunFailureCode, detail: str, path: str = "") -> None:
        super().__init__(f"{path}: {detail}" if path else detail)
        self.code = code
        self.path = path


class _UnsafeJson(ValueError):
    """JSON 文本预检失败，错误信息中没有原始字段或值。"""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _UnsafeJson("JSON 对象包含重复键")
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise _UnsafeJson("JSON 不允许非有限数")
    return number


def _reject_constant(_: str) -> None:
    raise _UnsafeJson("JSON 不允许非有限数")


def _schema_fields(schema: dict) -> set[str]:
    """提取已知字段供定位使用，避免回显模型可自行命名的任意额外键。"""
    result = set(schema.get("properties", {}))
    for value in schema.values():
        if isinstance(value, dict):
            result.update(_schema_fields(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    result.update(_schema_fields(item))
    return result


_SCHEMA_FIELDS = _schema_fields(TaskProposal.model_json_schema()) | {"spec", "task"}
_MAX_REPORTED_ERRORS = 5
_MAX_QUESTION_CHARS = TypeAdapter(BodyText).json_schema()["maxLength"]


def _pointer(location: tuple[str | int, ...]) -> str:
    # 复合输入类型的 spec/task 只是 Pydantic 判别分支，JSON Pointer 省略该段。
    segments = []
    for part in location:
        if part in {"spec", "task"}:
            continue
        segments.append(str(part) if isinstance(part, int) or part in _SCHEMA_FIELDS else "*")
    return "".join(f"/{part}" for part in segments)


def parse_proposal(response: ProviderResponse) -> TaskProposal:
    """检查截断和空白，再对整段 JSON 及共享模型进行严格验证。"""
    if response.finish_reason == "length":
        raise ProposalError(RunFailureCode.MODEL_TRUNCATED, "模型回复在输出完成前被截断")
    content = response.content
    if content is None or not content.strip():
        raise ProposalError(RunFailureCode.MODEL_EMPTY, "模型返回空白回复")
    if len(content) > MAX_BODY_BYTES:
        raise ProposalError(RunFailureCode.MODEL_SCHEMA, "模型回复超出解析大小上限")

    issue = None
    try:
        if len(content.encode("utf-8")) > MAX_BODY_BYTES:
            raise _UnsafeJson("模型回复超出解析大小上限")
        data = json.loads(
            content, object_pairs_hook=_unique_object, parse_float=_finite_float, parse_constant=_reject_constant
        )
        if not isinstance(data, dict):
            raise _UnsafeJson("回复必须是一个 JSON 对象")
    except _UnsafeJson as error:
        issue = str(error)
    except json.JSONDecodeError as error:
        issue = f"JSON 文本无效（第 {error.lineno} 行，第 {error.colno} 列）"
    except (ValueError, RecursionError):
        issue = "JSON 编码、数字或嵌套层级无效"
    if issue:
        raise ProposalError(RunFailureCode.MODEL_SCHEMA, issue)

    try:
        return TaskProposal.model_validate_json(content, strict=True)
    except ValidationError as error:
        errors = error.errors(include_input=False, include_context=False, include_url=False)
        details = [(_pointer(item["loc"]), item["type"]) for item in errors[:_MAX_REPORTED_ERRORS]]
    path = details[0][0]
    locations = "、".join(f"{location or '/'} ({kind})" for location, kind in details)
    raise ProposalError(RunFailureCode.MODEL_SCHEMA, f"提案结构不符合契约，检查 {locations}", path)


def with_blocking_questions(proposal: TaskProposal) -> TaskProposal:
    """保留原问题与关键假设，并在上限内追加可追溯的确认问题。"""
    questions = list(dict.fromkeys(proposal.blocking_questions))
    for task in proposal.tasks:
        for assumption in task.assumptions:
            if assumption.impact is not AssumptionImpact.CRITICAL:
                continue
            reference = f"请确认任务 {task.task_id} 的关键假设 {assumption.id}？"
            question = f"{reference}\n{assumption.text}"
            if len(question) <= _MAX_QUESTION_CHARS:
                _add_question(questions, question)
            else:
                # 合法假设正文可能已经占满单条问题的字符数，分别保留引用和正文。
                _add_question(questions, reference)
                _add_question(questions, assumption.text)
    if questions == proposal.blocking_questions:
        return proposal
    return TaskProposal.model_validate(
        {"schema_version": proposal.schema_version, "tasks": proposal.tasks, "blocking_questions": questions},
        strict=True,
    )


def _add_question(questions: list[str], question: str) -> None:
    wrapped = f"\n{question}\n"
    if any(wrapped in f"\n{existing}\n" for existing in questions):
        return
    if len(questions) < MAX_BLOCKING_QUESTIONS:
        questions.append(question)
        return
    # 已用足条数时保留原问题行，在仍有空间的条目中追加完整问题。
    for index in range(len(questions) - 1, -1, -1):
        combined = f"{questions[index]}\n{question}"
        if len(combined) <= _MAX_QUESTION_CHARS:
            questions[index] = combined
            return
    raise ProposalError(
        RunFailureCode.MODEL_SCHEMA,
        "阻塞问题已达契约上限，无法完整表达所有关键假设",
        "/blocking_questions",
    )

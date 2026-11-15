"""缺陷构造约定：Issue 的 path、severity 与定位信息统一从这里生成。

约定：
- `path` 是指向输入结构的 JSON Pointer，例如 `/tasks/2/dependencies/0`；
  报告只对同一份输入有效，前端用该路径直接定位到字段。
- severity 由错误码决定：契约只允许 `POSSIBLE_DUPLICATE` 和 `ORPHAN` 作为
  warning，其余错误码都是硬错误。这里按同一张表生成，避免构造出无法通过
  `Issue` 校验的对象。
- `suggestion` 只描述"怎么修"，不替用户决定业务方案。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from flowstudio_contracts import Issue, IssueCode, IssueSeverity, TaskEdge

#: 契约中唯一允许 warning 严重度的错误码；其余必须是 error。
ADVISORY_CODES: frozenset[IssueCode] = frozenset(
    {IssueCode.POSSIBLE_DUPLICATE, IssueCode.ORPHAN}
)


def pointer(*parts: str | int) -> str:
    """拼接 JSON Pointer；调用方只传已知字段名与下标，无需转义。"""
    return "".join(f"/{part}" for part in parts)


def task_path(index: int, *parts: str | int) -> str:
    return pointer("tasks", index, *parts)


def severity_for(code: IssueCode) -> IssueSeverity:
    return IssueSeverity.WARNING if code in ADVISORY_CODES else IssueSeverity.ERROR


def issue(
    code: IssueCode,
    path: str,
    message: str,
    *,
    task_ids: Sequence[str] = (),
    edges: Iterable[TaskEdge] = (),
    suggestion: str = "",
) -> Issue:
    """构造一条缺陷；task_ids 只放与缺陷直接相关的任务。"""
    return Issue(
        code=code,
        severity=severity_for(code),
        path=path,
        message=message,
        task_ids=list(dict.fromkeys(task_ids)),
        edges=list(edges),
        suggestion=suggestion,
    )


def normalize_text(value: str) -> str:
    """名称/交付文本的规范化：折叠空白并统一大小写，用于精确重复判定。

    只做确定性比较，不做相似度计算；语义相近仍由人工确认。
    """
    return " ".join(value.split()).casefold()


__all__ = [
    "ADVISORY_CODES",
    "issue",
    "normalize_text",
    "pointer",
    "severity_for",
    "task_path",
]

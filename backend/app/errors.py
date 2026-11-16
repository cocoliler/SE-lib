"""统一错误信封与异常类型。

错误体：{"error": {"code", "message", "issues", "request_id"}}

`code` 取自契约的 `ErrorCode`，`issues[].code` 取自 `IssueCode`；本模块不定义新码，
缺失语义回到 T01 补，避免前后端各自维护一套字符串。
"""

from __future__ import annotations

from typing import Any, Iterable

from flowstudio_contracts import (
    ErrorCode,
    Issue,
    IssueCode,
    IssueSeverity,
    TaskEdge,
)
from flowstudio_contracts.codes import ERROR_HTTP_STATUS


def make_issue(
    code: IssueCode,
    path: str,
    message: str,
    suggestion: str = "",
    *,
    task_ids: Iterable[str] = (),
    edges: Iterable[TaskEdge] = (),
) -> Issue:
    """构造契约 Issue；补齐必填的 task_ids/edges/suggestion。"""
    return Issue(
        code=code,
        severity=IssueSeverity.ERROR,
        path=path,
        message=message,
        task_ids=list(task_ids),
        edges=list(edges),
        suggestion=suggestion,
    )


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        issues: list[Issue] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.issues = issues or []


def _error(code: ErrorCode, message: str, issues: list[Issue] | None = None) -> ApiError:
    return ApiError(ERROR_HTTP_STATUS[code], code, message, issues)


def not_found(message: str) -> ApiError:
    return _error(ErrorCode.NOT_FOUND, message)


def revision_conflict(current_revision: int, message: str = "") -> ApiError:
    return _error(
        ErrorCode.REVISION_CONFLICT,
        message or f"版本已变化，当前版本为 {current_revision}",
    )


def idempotency_conflict(message: str = "同一 Idempotency-Key 对应了不同请求内容") -> ApiError:
    return _error(ErrorCode.IDEMPOTENCY_CONFLICT, message)


def validation_failed(message: str, issues: list[Issue] | None = None) -> ApiError:
    return _error(ErrorCode.VALIDATION_FAILED, message, issues)


def source_mismatch(message: str) -> ApiError:
    return _error(
        ErrorCode.VALIDATION_FAILED,
        message,
        [
            make_issue(
                IssueCode.SOURCE_MISMATCH,
                "/planning_run_id",
                message,
                "核对 planning_run_id 对应的项目、规格版本与规划参数",
            )
        ],
    )


def result_not_ready(message: str = "规划尚未成功完成") -> ApiError:
    return _error(ErrorCode.RESULT_NOT_READY, message)


def payload_too_large(limit: int) -> ApiError:
    return _error(ErrorCode.PAYLOAD_TOO_LARGE, f"请求体超过 {limit} 字节上限")


def queue_full() -> ApiError:
    return _error(ErrorCode.QUEUE_FULL, "规划队列已满，请稍后重试")


def storage_busy() -> ApiError:
    return _error(ErrorCode.STORAGE_BUSY, "本地数据库繁忙（写锁超过 5 秒），本次未保存成功")


def forbidden_host_or_origin(message: str) -> ApiError:
    return _error(ErrorCode.ORIGIN_FORBIDDEN, message)


def error_body(
    code: ErrorCode | str,
    message: str,
    issues: list[Issue] | None,
    request_id: str,
) -> dict[str, Any]:
    return {
        "error": {
            "code": str(code),
            "message": message,
            "issues": [issue.model_dump(mode="json") for issue in (issues or [])],
            "request_id": request_id,
        }
    }

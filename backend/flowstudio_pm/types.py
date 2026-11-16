"""PM 模块内部使用的模型调用参数与返回值。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, TypedDict

from flowstudio_contracts import TokenUsage
from flowstudio_contracts.constants import MAX_OUTPUT_TOKENS, PLANNING_REQUEST_TIMEOUT_SECONDS


class Message(TypedDict):
    role: Literal["system", "user"]
    content: str


@dataclass(frozen=True, slots=True)
class ModelLimits:
    """由服务端配置的单模型上下文和输出上限。"""

    context_tokens: int
    max_output_tokens: int

    def __post_init__(self) -> None:
        if (
            type(self.context_tokens) is not int
            or type(self.max_output_tokens) is not int
            or not 0 < self.max_output_tokens < self.context_tokens
        ):
            raise ValueError("模型上下文和输出限额必须为有效的正整数")


def validate_completion_options(max_tokens: int, timeout_seconds: float, limits: ModelLimits) -> None:
    """在调用前检查项目预算与当前模型限额。"""
    if (
        type(max_tokens) is not int
        or not 0 < max_tokens <= min(MAX_OUTPUT_TOKENS, limits.max_output_tokens)
    ):
        raise ValueError("模型请求输出限额无效")
    if (
        type(timeout_seconds) not in (int, float)
        or not 0 < timeout_seconds <= PLANNING_REQUEST_TIMEOUT_SECONDS
        or not math.isfinite(timeout_seconds)
    ):
        raise ValueError("模型请求超时无效")


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """单次响应。内容只供解析与受限修复，省略在对象摘要中的显示。"""

    content: str | None = field(repr=False)
    usage: TokenUsage | None = None
    request_id: str | None = None
    finish_reason: str | None = None


class ProviderFailureKind(StrEnum):
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    TRANSIENT_SERVER = "transient_server"
    INVALID_RESPONSE = "invalid_response"


_FAILURE_MESSAGES = {
    ProviderFailureKind.AUTH: "模型服务认证失败",
    ProviderFailureKind.RATE_LIMIT: "模型服务限流",
    ProviderFailureKind.TIMEOUT: "模型请求超时",
    ProviderFailureKind.NETWORK: "模型服务连接失败",
    ProviderFailureKind.TRANSIENT_SERVER: "模型服务暂不可用",
    ProviderFailureKind.INVALID_RESPONSE: "模型服务响应格式无效",
}


class ProviderFailure(Exception):
    """单次请求失败，可保留通过凭据检查的回复正文供显式验收。"""

    def __init__(
        self,
        kind: ProviderFailureKind,
        *,
        request_id: str | None = None,
        usage: TokenUsage | None = None,
        finish_reason: str | None = None,
        content: str | None = None,
    ) -> None:
        super().__init__(_FAILURE_MESSAGES[kind])
        self.kind = kind
        self.request_id = request_id
        self.usage = usage
        self.finish_reason = finish_reason
        self.content = content

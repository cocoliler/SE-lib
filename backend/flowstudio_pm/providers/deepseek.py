"""DeepSeek 官方 Chat Completions JSON 模式单请求适配。"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping, Sequence

import httpx
from flowstudio_contracts import PlanningMode, TokenUsage
from flowstudio_contracts.constants import MAX_BODY_BYTES

from ..types import (
    Message,
    ModelLimits,
    ProviderFailure,
    ProviderFailureKind,
    ProviderResponse,
    validate_completion_options,
)

_API_URL = "https://api.deepseek.com/chat/completions"
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}")
_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}")
_FINISH_REASONS = frozenset({"stop", "length", "content_filter", "tool_calls", "insufficient_system_resource"})

def _usage_count(raw_value: object) -> int | None:
    return raw_value if type(raw_value) is int and raw_value >= 0 else None


def _parse_usage(raw_usage: object) -> TokenUsage | None:
    if not isinstance(raw_usage, dict):
        return None
    prompt = _usage_count(raw_usage.get("prompt_tokens"))
    completion = _usage_count(raw_usage.get("completion_tokens"))
    total = _usage_count(raw_usage.get("total_tokens"))
    known_parts = (prompt or 0) + (completion or 0)
    # 不一致时保留可用于保守记账的较大一侧，无法同时成立的数值保持未知。
    if total is not None:
        if known_parts > total:
            total = None
        elif prompt is not None and completion is not None and total > known_parts:
            prompt = completion = None
    return TokenUsage(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)


def _http_failure(status: int) -> ProviderFailureKind:
    if status in (401, 403):
        return ProviderFailureKind.AUTH
    if status == 429:
        return ProviderFailureKind.RATE_LIMIT
    if status == 408:
        return ProviderFailureKind.TIMEOUT
    if status in (500, 502, 503, 504):
        return ProviderFailureKind.TRANSIENT_SERVER
    return ProviderFailureKind.INVALID_RESPONSE


class DeepSeekProvider:
    """服务端创建并持有 AsyncClient，凭据和模型白名单由调用方显式注入。"""

    mode = PlanningMode.REAL
    fixture_id = None

    def __init__(
        self,
        *,
        api_key: str,
        allowed_models: Mapping[str, ModelLimits],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key or not all(33 <= ord(char) <= 126 for char in api_key):
            raise ValueError("缺少有效的 DeepSeek API 凭据")
        if not allowed_models or any(
            not isinstance(name, str) or not _MODEL_NAME.fullmatch(name) or not isinstance(limits, ModelLimits)
            for name, limits in allowed_models.items()
        ):
            raise ValueError("DeepSeek 模型白名单配置无效")
        self._api_key = api_key
        self._allowed_models = dict(allowed_models)
        if transport is None:
            transport = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        )

    def model_limits(self, model: str) -> ModelLimits:
        if not isinstance(model, str) or model not in self._allowed_models:
            raise ValueError("未启用所选 DeepSeek 模型")
        return self._allowed_models[model]

    def _safe_request_id(self, value: object) -> str | None:
        if isinstance(value, str) and _REQUEST_ID.fullmatch(value) and self._api_key not in value:
            return value
        return None

    async def complete_json(
        self,
        *,
        messages: Sequence[Message],
        model: str,
        max_tokens: int,
        timeout_seconds: float,
    ) -> ProviderResponse:
        """发送一个不重试、不跟随跳转的请求，超时覆盖整个请求与响应读取。"""
        validate_completion_options(max_tokens, timeout_seconds, self.model_limits(model))
        if self._client.is_closed:
            raise ValueError("DeepSeek Provider 已关闭")
        payload = {
            "model": model,
            "messages": list(messages),
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        request_id = None
        try:
            async with asyncio.timeout(timeout_seconds):
                async with self._client.stream(
                    "POST", _API_URL, json=payload, timeout=timeout_seconds, follow_redirects=False
                ) as response:
                    request_id = self._safe_request_id(response.headers.get("x-request-id"))
                    if not response.is_success:
                        raise ProviderFailure(_http_failure(response.status_code), request_id=request_id)
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > MAX_BODY_BYTES:
                            raise ProviderFailure(ProviderFailureKind.INVALID_RESPONSE, request_id=request_id)
                        content.extend(chunk)
        except (TimeoutError, httpx.TimeoutException):
            failure = ProviderFailureKind.TIMEOUT
        except httpx.DecodingError:
            failure = ProviderFailureKind.INVALID_RESPONSE
        except httpx.RequestError:
            failure = ProviderFailureKind.NETWORK
        else:
            return self._parse_response(content, request_id)
        # 离开捕获块后构造脱敏异常，避免 SDK 异常出现在异常链中。
        raise ProviderFailure(failure, request_id=request_id)

    def _parse_response(self, content: bytearray, request_id: str | None) -> ProviderResponse:
        try:
            payload = json.loads(content.decode("utf-8"))
        except (ValueError, RecursionError):
            payload = None
        if not isinstance(payload, dict):
            raise ProviderFailure(ProviderFailureKind.INVALID_RESPONSE, request_id=request_id)
        request_id = request_id or self._safe_request_id(payload.get("id"))
        usage = _parse_usage(payload.get("usage"))
        choices = payload.get("choices")
        if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict):
            choice = choices[0]
            message = choice.get("message")
            finish = choice.get("finish_reason")
            if isinstance(message, dict) and "content" in message:
                text = message["content"]
                safe_finish = finish is None or isinstance(finish, str) and finish in _FINISH_REASONS
                safe_content = text is None or isinstance(text, str) and self._api_key not in text
                if safe_finish and safe_content:
                    return ProviderResponse(text, usage=usage, request_id=request_id, finish_reason=finish)
        raise ProviderFailure(ProviderFailureKind.INVALID_RESPONSE, request_id=request_id, usage=usage)

    async def aclose(self) -> None:
        """关闭当前 Provider 持有的客户端与连接池。"""
        await self._client.aclose()

    async def __aenter__(self) -> DeepSeekProvider:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

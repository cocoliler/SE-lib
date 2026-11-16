"""PM 依赖的单次模型调用接口。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from flowstudio_contracts import PlanningMode

from .types import Message, ModelLimits, ProviderResponse


class LLMProvider(Protocol):
    @property
    def mode(self) -> PlanningMode: ...

    @property
    def fixture_id(self) -> str | None: ...

    def model_limits(self, model: str) -> ModelLimits:
        """返回允许的模型能力；无匹配时抛出 ValueError。"""
        ...

    async def complete_json(
        self,
        *,
        messages: Sequence[Message],
        model: str,
        max_tokens: int,
        timeout_seconds: float,
    ) -> ProviderResponse:
        """只发起一次请求，失败归一为 ProviderFailure，取消向上传播。"""
        ...

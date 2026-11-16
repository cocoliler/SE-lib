"""显式选择的离线测试 Provider。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from flowstudio_contracts import PlanningMode
from flowstudio_contracts.constants import MAX_OUTPUT_TOKENS, TOKEN_RESERVE_PER_RUN

from ..types import Message, ModelLimits, ProviderResponse, validate_completion_options


class TestFixtureProvider:
    """从注入的测试样例中选择响应，复用正常响应解析与预算通路。"""

    mode = PlanningMode.TEST

    def __init__(self, *, fixture_id: str, fixtures: Mapping[str, ProviderResponse]) -> None:
        if not isinstance(fixture_id, str) or not fixture_id.strip() or fixture_id not in fixtures:
            raise ValueError("测试模式需要明确且已登记的 fixture_id")
        self._fixture_id = fixture_id
        self._response = fixtures[fixture_id]
        if not isinstance(self._response, ProviderResponse):
            raise ValueError("fixture 必须是已构造的 ProviderResponse")

    @property
    def fixture_id(self) -> str:
        return self._fixture_id

    def model_limits(self, model: str) -> ModelLimits:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("测试模式缺少有效模型名")
        return ModelLimits(TOKEN_RESERVE_PER_RUN, MAX_OUTPUT_TOKENS)

    async def complete_json(
        self,
        *,
        messages: Sequence[Message],
        model: str,
        max_tokens: int,
        timeout_seconds: float,
    ) -> ProviderResponse:
        validate_completion_options(max_tokens, timeout_seconds, self.model_limits(model))
        return self._response

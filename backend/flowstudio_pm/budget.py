"""单次规划的尝试、期限和 Token 预留记账。"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from flowstudio_contracts import RunFailureCode, TokenUsage
from flowstudio_contracts.constants import (
    MAX_OUTPUT_TOKENS,
    MAX_PLANNING_ATTEMPTS,
    PLANNING_DEADLINE_SECONDS,
    PLANNING_REQUEST_TIMEOUT_SECONDS,
    TOKEN_RESERVE_PER_RUN,
)

from .types import ModelLimits


class BudgetError(Exception):
    """本地限额未满足，携带可直接用于 RunError 的诊断。"""

    def __init__(self, code: RunFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class RunBudget:
    """运行内同步扣账；每个实际请求各记一笔，完成后只结算一次。"""

    def __init__(self, monotonic: Callable[[], float], *, elapsed_before_start: float = 0.0) -> None:
        self.monotonic = monotonic
        self.deadline = monotonic() + PLANNING_DEADLINE_SECONDS - elapsed_before_start
        self.attempt_count = 0
        self.accounted_tokens = 0

    @property
    def remaining_seconds(self) -> float:
        return self.deadline - self.monotonic()

    @property
    def has_attempts(self) -> bool:
        return self.attempt_count < MAX_PLANNING_ATTEMPTS

    def check_deadline(self) -> None:
        if self.remaining_seconds <= 0:
            raise BudgetError(RunFailureCode.MODEL_TIMEOUT, "规划已达到总截止时间")

    def reserve(self, input_tokens: int, output_tokens: int, limits: ModelLimits) -> tuple[int, float]:
        """先检查期限、上下文和可用预算，再预留固定输出额度及估计输入。"""
        if type(input_tokens) is not int or input_tokens < 1:
            raise ValueError("输入 Token 估算必须为正整数")
        remaining = self.remaining_seconds
        if remaining <= 0:
            raise BudgetError(RunFailureCode.MODEL_TIMEOUT, "规划已达到总截止时间")
        if not self.has_attempts:
            raise BudgetError(RunFailureCode.MODEL_BUDGET, "规划已达到模型尝试上限")
        reserved = input_tokens + MAX_OUTPUT_TOKENS
        if input_tokens + output_tokens > limits.context_tokens:
            raise BudgetError(RunFailureCode.MODEL_BUDGET, "模型请求超过所配置的上下文窗口")
        if self.accounted_tokens + reserved > TOKEN_RESERVE_PER_RUN:
            raise BudgetError(RunFailureCode.MODEL_BUDGET, "剩余 Token 预算不足以预留本次请求")
        self.attempt_count += 1
        self.accounted_tokens += reserved
        return reserved, min(PLANNING_REQUEST_TIMEOUT_SECONDS, remaining)

    def settle(self, reserved: int, usage: TokenUsage | None) -> tuple[int, bool]:
        """按完整用量或更高的已知用量下界结算；部分未知不退回预留。"""
        if usage is None:
            return reserved, True
        prompt, completion, total = usage.prompt_tokens, usage.completion_tokens, usage.total_tokens
        unknown = prompt is None or completion is None or total is None
        accounted = max(reserved, total or 0, (prompt or 0) + (completion or 0)) if unknown else total
        self.accounted_tokens += accounted - reserved
        return accounted, unknown

    def check_accounted_tokens(self) -> None:
        if self.accounted_tokens > TOKEN_RESERVE_PER_RUN:
            raise BudgetError(RunFailureCode.MODEL_BUDGET, "模型报告的用量已超出规划 Token 预算")


def aggregate_usage(attempts: Sequence[TokenUsage | None]) -> TokenUsage:
    """按分量合计；任一尝试的该分量未知时，结果同一分量保持 null。"""
    fields: dict[str, int | None] = {}
    for field in TokenUsage.model_fields:
        values = [getattr(attempt, field, None) for attempt in attempts]
        fields[field] = sum(value for value in values if value is not None) if values and None not in values else None
    return TokenUsage.model_validate(fields)

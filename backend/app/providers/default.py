"""Dispatch local fixtures and configured DeepSeek planning runs."""

from __future__ import annotations

import asyncio
from pathlib import Path

from flowstudio_contracts import PlanningConfig, PlanningMode, RunError, RunFailureCode, SpecRevision
from flowstudio_contracts.constants import MAX_OUTPUT_TOKENS, TOKEN_RESERVE_PER_RUN
from flowstudio_pm.planner import GraphFailure, generate_validated_proposal
from flowstudio_pm.providers.deepseek import DeepSeekProvider
from flowstudio_pm.types import ModelLimits

from .base import AttemptRecord, PlanningOutcome
from .fixtures import FixtureEngine


class DefaultPlanningEngine:
    def __init__(
        self, fixtures_dir: Path | None, *, api_key: str = "", models: tuple[str, ...] = ()
    ) -> None:
        self.fixture_engine = FixtureEngine(fixtures_dir)
        self._api_key = api_key
        # DeepSeek supports more context than the application's total run budget.
        self._models = {model: ModelLimits(TOKEN_RESERVE_PER_RUN, MAX_OUTPUT_TOKENS) for model in models}

    def fixtures(self) -> tuple[str, ...]:
        return self.fixture_engine.fixtures()

    def plan(
        self,
        *,
        mode: PlanningMode,
        spec_revision: SpecRevision,
        config: PlanningConfig,
        fixture_id: str | None,
        run_id: str,
    ) -> PlanningOutcome:
        if mode is PlanningMode.TEST:
            return self.fixture_engine.plan(
                mode=mode, spec_revision=spec_revision, config=config, fixture_id=fixture_id, run_id=run_id
            )
        return asyncio.run(self._plan_real(spec_revision, config))

    async def _plan_real(self, spec_revision: SpecRevision, config: PlanningConfig) -> PlanningOutcome:
        if not self._api_key:
            return PlanningOutcome(error=RunError(
                code=RunFailureCode.MODEL_AUTH,
                message="后端未配置 DEEPSEEK_API_KEY，请设置后重启后端。",
                retryable=False,
            ))

        try:
            provider = DeepSeekProvider(api_key=self._api_key, allowed_models=self._models)
        except ValueError as error:
            return PlanningOutcome(error=RunError(
                code=RunFailureCode.MODEL_AUTH, message=str(error), retryable=False
            ))

        async with provider:
            result = await generate_validated_proposal(spec_revision, config, PlanningMode.REAL, provider)

        proposal, error = result.proposal, result.error
        if error is None and result.graph_failure is not None:
            if result.graph_failure is GraphFailure.INVALID and result.latest_report_check is not None:
                # The coordinator will record the rule violations with the terminal run.
                proposal = result.latest_report_check.proposal
            else:
                limit = result.graph_failure is GraphFailure.LIMIT
                error = RunError(
                    code=RunFailureCode.MODEL_SCHEMA if limit else RunFailureCode.INTERNAL_ERROR,
                    message="候选任务的依赖规模超过上限" if limit else "候选任务图校验未完成",
                    retryable=False,
                )
        return PlanningOutcome(
            proposal=proposal,
            error=error,
            usage=result.usage,
            attempts=[
                AttemptRecord(
                    attempt_no=item.index,
                    request_hash=item.prompt_hash,
                    response={"response_hash": item.response_hash, "finish_reason": item.finish_reason},
                    usage=item.actual_usage.model_dump(mode="json") if item.actual_usage else None,
                    error={"code": item.error_code.value} if item.error_code else None,
                )
                for item in result.diagnostics
            ],
        )

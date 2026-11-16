"""默认引擎分发：TEST → fixture；REAL → 未配置占位（真实适配器属 C 的 T04）。

刻意不伪造 REAL 结果：没有 DeepSeekAdapter 时 REAL 请求以 MODEL_AUTH 失败并保留诊断，
不静默降级成 TEST。
"""

from __future__ import annotations

from pathlib import Path

from flowstudio_contracts import (
    PlanningConfig,
    PlanningMode,
    RunError,
    RunFailureCode,
    SpecRevision,
)

from .base import AttemptRecord, PlanningOutcome
from .fixtures import FixtureEngine


class DefaultPlanningEngine:
    def __init__(self, fixtures_dir: Path | None) -> None:
        self.fixture_engine = FixtureEngine(fixtures_dir)

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
                mode=mode,
                spec_revision=spec_revision,
                config=config,
                fixture_id=fixture_id,
                run_id=run_id,
            )
        return PlanningOutcome(
            error=RunError(
                code=RunFailureCode.MODEL_AUTH,
                message=(
                    "未配置真实模型适配器（由 C 的 T04 提供 DeepSeekAdapter）。"
                    "当前可用 TEST fixture 验证结构；REAL 不会静默降级。"
                ),
                retryable=False,
            ),
            attempts=[
                AttemptRecord(
                    attempt_no=1,
                    request_hash="",
                    error={"code": "MODEL_AUTH", "message": "no real adapter"},
                )
            ],
        )

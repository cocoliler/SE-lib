"""PlanningRun 协调器：领取 → 调用 PM 引擎 → 结构/图校验 → 终态写回。

模型调用永远在数据库事务外；状态迁移严格按
QUEUED → RUNNING → SUCCEEDED / NEEDS_INPUT / FAILED。
图校验调用 T05 编排器，不在本层重复实现算法。
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import sessionmaker

from flowstudio_contracts import (
    AssumptionImpact,
    PlanningConfig,
    PlanningMode,
    PlanningStatus,
    RunError,
    RunFailureCode,
    SpecRevision,
    ValidationReport,
)
from flowstudio_contracts.codes import RETRYABLE_RUN_FAILURES
from flowstudio_contracts.constants import MAX_PLANNING_ATTEMPTS
from flowstudio_orchestration import build_plan

from ..persistence import repos
from ..persistence.tables import PlanningRunRow
from ..providers.base import PlanningEngine, PlanningOutcome

LOGGER = logging.getLogger(__name__)


def _run_error(code: RunFailureCode, message: str) -> RunError:
    return RunError(code=code, message=message, retryable=code in RETRYABLE_RUN_FAILURES)


class PlanningCoordinator:
    def __init__(self, sessionmaker_: sessionmaker, engine: PlanningEngine) -> None:
        self.sessionmaker = sessionmaker_
        self.engine = engine

    # ------------------------------------------------------------------ public
    def process(self, run_id: str) -> None:
        with self.sessionmaker() as session:
            row = session.get(PlanningRunRow, run_id)
            if row is None or row.status != PlanningStatus.QUEUED.value:
                return
            if not repos.mark_run_running(session, run_id):
                session.rollback()
                return
            session.commit()
            spec_revision_id = row.spec_revision_id
            mode = PlanningMode(row.mode)
            config = PlanningConfig.model_validate_json(row.config_json)
            fixture_id = row.fixture_id

        try:
            with self.sessionmaker() as session:
                spec_revision, _ = repos.get_spec_revision(session, spec_revision_id)
        except Exception:  # noqa: BLE001
            LOGGER.exception("读取规格版本失败：%s", spec_revision_id)
            failed = PlanningOutcome(
                error=_run_error(RunFailureCode.INTERNAL_ERROR, "读取规格版本失败")
            )
            self._finish(run_id, failed, PlanningStatus.FAILED, failed.error, None)
            return

        try:
            outcome = self.engine.plan(
                mode=mode,
                spec_revision=spec_revision,
                config=config,
                fixture_id=fixture_id,
                run_id=run_id,
            )
        except Exception as exc:  # noqa: BLE001 - 任何引擎异常都必须落成显式失败
            LOGGER.exception("规划引擎异常：%s", run_id)
            outcome = PlanningOutcome(
                error=_run_error(RunFailureCode.INTERNAL_ERROR, f"规划引擎异常：{exc}")
            )

        status, error, report = self._decide(outcome, spec_revision, config)
        self._finish(run_id, outcome, status, error, report)

    # ----------------------------------------------------------------- helpers
    def _decide(
        self, outcome: PlanningOutcome, spec_revision: SpecRevision, config: PlanningConfig
    ) -> tuple[PlanningStatus, RunError | None, ValidationReport | None]:
        if len(outcome.attempts) > MAX_PLANNING_ATTEMPTS:
            return (
                PlanningStatus.FAILED,
                _run_error(
                    RunFailureCode.MODEL_BUDGET,
                    f"模型调用 {len(outcome.attempts)} 次超过上限 {MAX_PLANNING_ATTEMPTS}",
                ),
                None,
            )
        if outcome.error is not None:
            return PlanningStatus.FAILED, outcome.error, None

        proposal = outcome.proposal
        if proposal is None:
            return (
                PlanningStatus.FAILED,
                _run_error(RunFailureCode.MODEL_EMPTY, "模型返回空候选"),
                None,
            )

        if proposal.blocking_questions:
            return PlanningStatus.NEEDS_INPUT, None, None

        critical = [
            assumption
            for task in proposal.tasks
            for assumption in task.assumptions
            if assumption.impact is AssumptionImpact.CRITICAL
        ]
        if critical:
            return PlanningStatus.NEEDS_INPUT, None, None

        build = build_plan(proposal.tasks, spec_revision.content, config.policy)
        if not build.validation_report.valid:
            first = build.validation_report.errors[0] if build.validation_report.errors else None
            message = (
                f"{first.code}: {first.message}" if first is not None else "候选未通过结构与图校验"
            )
            return (
                PlanningStatus.FAILED,
                _run_error(RunFailureCode.MODEL_SCHEMA, message),
                build.validation_report,
            )
        return PlanningStatus.SUCCEEDED, None, build.validation_report

    def _finish(
        self,
        run_id: str,
        outcome: PlanningOutcome,
        status: PlanningStatus | None,
        error: RunError | None,
        report: ValidationReport | None,
    ) -> None:
        status = status or PlanningStatus.FAILED
        with self.sessionmaker() as session:
            for attempt in outcome.attempts[:MAX_PLANNING_ATTEMPTS]:
                repos.add_attempt(
                    session,
                    run_id=run_id,
                    attempt_no=attempt.attempt_no,
                    request_hash=attempt.request_hash,
                    response=attempt.response,
                    usage=attempt.usage,
                    error=attempt.error,
                )
            repos.finish_run(
                session,
                run_id,
                status=status,
                proposal=outcome.proposal,
                report=report,
                error=error,
                usage=outcome.usage,
                attempt_count=len(outcome.attempts),
            )
            session.commit()

"""PM 候选生成的有界修复、预算和失败隔离测试。"""

import asyncio
import json
import unittest

import pm_support
from flowstudio_contracts import PlanningMode, RunFailureCode, TaskProposal, TokenUsage
from flowstudio_contracts.constants import MAX_OUTPUT_TOKENS, TOKEN_RESERVE_PER_RUN
from flowstudio_pm.planner import ProposalKind, generate_proposal
from flowstudio_pm.providers.fixture import TestFixtureProvider
from flowstudio_pm.types import ModelLimits, ProviderFailure, ProviderFailureKind, ProviderResponse


CANDIDATE = pm_support.example("task-proposal")
BLOCKED = pm_support.example("task-proposal-blocked")
USAGE = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
MODEL_LIMITS = ModelLimits(context_tokens=120_000, max_output_tokens=MAX_OUTPUT_TOKENS)


class Clock:
    def __init__(self):
        self.now = 10.0
        self.pauses = []

    def monotonic(self):
        return self.now

    async def sleep(self, seconds):
        self.pauses.append(seconds)
        self.now += seconds


class SequenceProvider:
    mode = PlanningMode.REAL
    fixture_id = None

    def __init__(self, *results, limits=MODEL_LIMITS):
        self.results = iter(results)
        self.limits = limits
        self.calls = []

    def model_limits(self, model):
        if model != "test-model":
            raise ValueError("model rejected")
        return self.limits

    async def complete_json(self, **options):
        self.calls.append(options)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result() if callable(result) else result


class PlannerTests(unittest.IsolatedAsyncioTestCase):
    async def run_plan(self, provider, *, clock=None, **changes):
        clock = clock or Clock()
        return await generate_proposal(
            **{
                "spec": pm_support.spec_revision(),
                "config": pm_support.config(),
                "mode": PlanningMode.REAL,
                "provider": provider,
                "monotonic": clock.monotonic,
                "sleep": clock.sleep,
                "estimate_input_tokens": lambda _: 100,
                **changes,
            }
        )

    async def test_known_fixture_follows_shared_parser_and_keeps_test_provenance(self):
        provider = TestFixtureProvider(fixture_id="candidate", fixtures={"candidate": ProviderResponse(CANDIDATE)})
        result = await self.run_plan(provider, mode=PlanningMode.TEST, fixture_id="candidate")
        self.assertIs(result.kind, ProposalKind.CANDIDATE)
        self.assertIs(result.mode, PlanningMode.TEST)
        self.assertEqual(result.fixture_id, "candidate")
        self.assertEqual(result.attempt_count, 1)
        self.assertEqual(result.proposal, TaskProposal.model_validate_json(CANDIDATE))
        self.assertIsNone(result.error)
        self.assertEqual(result.usage, TokenUsage())
        self.assertTrue(result.diagnostics[0].usage_unknown)

    async def test_plain_questions_and_critical_assumptions_block_and_low_is_preserved(self):
        blocked = await self.run_plan(SequenceProvider(ProviderResponse(BLOCKED, USAGE)))
        self.assertIs(blocked.kind, ProposalKind.NEEDS_INPUT)
        self.assertEqual(blocked.proposal.tasks, [])
        self.assertTrue(blocked.proposal.blocking_questions)

        payload = json.loads(CANDIDATE)
        payload["tasks"][0]["assumptions"] = [{"id": "A-edge", "text": "必须确认角色", "impact": "critical"}]
        critical = await self.run_plan(SequenceProvider(ProviderResponse(json.dumps(payload), USAGE)))
        self.assertIs(critical.kind, ProposalKind.NEEDS_INPUT)
        self.assertIn("A-edge", critical.proposal.blocking_questions[0])
        self.assertEqual(critical.proposal.critical_assumption_ids, ["A-edge"])
        self.assertIsNone(critical.error)

        payload["tasks"][0]["assumptions"][0]["impact"] = "low"
        low = await self.run_plan(SequenceProvider(ProviderResponse(json.dumps(payload), USAGE)))
        self.assertIs(low.kind, ProposalKind.CANDIDATE)
        self.assertIn("A-edge", low.proposal.low_assumption_ids)
        self.assertEqual(low.proposal.blocking_questions, [])

    async def test_mode_fixture_validation_precedes_any_attempt(self):
        real = SequenceProvider()
        test = TestFixtureProvider(fixture_id="candidate", fixtures={"candidate": ProviderResponse(CANDIDATE)})
        for provider, mode, fixture_id in (
            (real, PlanningMode.REAL, "candidate"),
            (real, PlanningMode.TEST, "candidate"),
            (test, PlanningMode.REAL, None),
            (test, PlanningMode.TEST, None),
            (test, PlanningMode.TEST, "candidate-other"),
            (real, "REAL", None),
        ):
            with self.subTest(mode=mode, fixture_id=fixture_id):
                result = await self.run_plan(provider, mode=mode, fixture_id=fixture_id)
                self.assertIs(result.kind, ProposalKind.FAILED)
                self.assertIs(result.error.code, RunFailureCode.INTERNAL_ERROR)
                self.assertEqual(result.attempt_count, 0)
        self.assertEqual(real.calls, [])

    async def test_repair_uses_same_input_and_audit_only_keeps_hashes(self):
        spec = pm_support.spec_revision(supplemental_text="原输入")
        def first():
            spec.content.supplemental_text = "并发修改后输入"
            return ProviderResponse("private-model-output", USAGE, request_id="request-1")

        provider = SequenceProvider(first, ProviderResponse(CANDIDATE, USAGE))
        result = await self.run_plan(provider, spec=spec)
        self.assertIs(result.kind, ProposalKind.CANDIDATE)
        self.assertEqual(result.usage, TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30))
        original = json.loads(provider.calls[0]["messages"][1]["content"])
        repair = json.loads(provider.calls[1]["messages"][1]["content"])
        feedback = repair.pop("repair")
        self.assertEqual(original, repair)
        self.assertEqual(repair["spec"]["supplemental_text"], "原输入")
        self.assertEqual(feedback["code"], "MODEL_SCHEMA")
        self.assertEqual(feedback["previous_content"], "private-model-output")
        self.assertIs(result.diagnostics[0].error_code, RunFailureCode.MODEL_SCHEMA)
        self.assertIsNone(result.diagnostics[1].error_code)
        self.assertEqual(result.diagnostics[0].provider_request_id, "request-1")
        self.assertEqual(len(result.diagnostics[0].response_hash), 64)
        self.assertNotEqual(result.diagnostics[0].prompt_hash, result.diagnostics[1].prompt_hash)
        self.assertNotIn("private-model-output", repr(result))
        self.assertNotIn("原输入", repr(result))

    async def test_length_and_empty_repair_share_three_attempts(self):
        provider = SequenceProvider(
            ProviderResponse("", USAGE, finish_reason="length"),
            ProviderResponse(" ", USAGE, finish_reason="stop"),
            ProviderResponse("not-json", USAGE),
            ProviderResponse(CANDIDATE, USAGE),
        )
        result = await self.run_plan(provider)
        self.assertIs(result.kind, ProposalKind.FAILED)
        self.assertEqual(result.attempt_count, 3)
        self.assertEqual(len(provider.calls), 3)
        self.assertEqual([item.error_code for item in result.diagnostics], [
            RunFailureCode.MODEL_TRUNCATED, RunFailureCode.MODEL_EMPTY, RunFailureCode.MODEL_SCHEMA
        ])
        self.assertIs(result.error.code, RunFailureCode.MODEL_SCHEMA)

    async def test_429_or_transient_5xx_retries_once_within_same_three_attempts(self):
        for transient in (ProviderFailureKind.RATE_LIMIT, ProviderFailureKind.TRANSIENT_SERVER):
            clock = Clock()
            failure = ProviderFailure(transient, request_id="retry-request")
            provider = SequenceProvider(ProviderResponse("bad", USAGE), failure, ProviderResponse(CANDIDATE, USAGE))
            result = await self.run_plan(provider, clock=clock)
            self.assertIs(result.kind, ProposalKind.CANDIDATE)
            self.assertEqual(result.attempt_count, 3)
            self.assertEqual(provider.calls[1]["messages"], provider.calls[2]["messages"])
            self.assertEqual(len(clock.pauses), 1)
            self.assertGreaterEqual(clock.pauses[0], 1)
            self.assertLessEqual(clock.pauses[0], 3)
            self.assertEqual(result.diagnostics[1].provider_failure, transient)
            self.assertEqual(result.diagnostics[1].provider_request_id, "retry-request")
            self.assertEqual(result.usage, TokenUsage())

        clock = Clock()
        provider = SequenceProvider(
            ProviderFailure(ProviderFailureKind.RATE_LIMIT),
            ProviderFailure(ProviderFailureKind.TRANSIENT_SERVER),
            ProviderResponse(CANDIDATE, USAGE),
        )
        result = await self.run_plan(provider, clock=clock)
        self.assertIs(result.error.code, RunFailureCode.MODEL_NETWORK)
        self.assertEqual(result.attempt_count, 2)
        self.assertEqual(len(clock.pauses), 1)

    async def test_auth_timeout_and_network_are_terminal_without_fallback(self):
        for kind, code, retryable in (
            (ProviderFailureKind.AUTH, RunFailureCode.MODEL_AUTH, False),
            (ProviderFailureKind.TIMEOUT, RunFailureCode.MODEL_TIMEOUT, True),
            (ProviderFailureKind.NETWORK, RunFailureCode.MODEL_NETWORK, True),
            (ProviderFailureKind.INVALID_RESPONSE, RunFailureCode.MODEL_SCHEMA, False),
        ):
            clock = Clock()
            provider = SequenceProvider(ProviderFailure(kind), ProviderResponse(CANDIDATE, USAGE))
            result = await self.run_plan(provider, clock=clock)
            self.assertIs(result.kind, ProposalKind.FAILED)
            self.assertIsNone(result.proposal)
            self.assertIs(result.error.code, code)
            self.assertIs(result.error.retryable, retryable)
            self.assertEqual(result.attempt_count, 1)
            self.assertEqual(clock.pauses, [])

    async def test_deadline_shrinks_next_timeout_and_rejects_late_response(self):
        clock = Clock()
        def response_after(seconds, response):
            def result():
                clock.now += seconds
                return response
            return result

        provider = SequenceProvider(
            response_after(59, ProviderResponse("bad", USAGE)),
            response_after(59, ProviderResponse("bad", USAGE)),
            response_after(63, ProviderResponse(CANDIDATE, USAGE)),
        )
        def advancing_estimate(_):
            # 注入本地处理时间：总期限包含预留和请求间的 Prompt 处理。
            clock.now += 10
            return 100

        result = await self.run_plan(provider, clock=clock, estimate_input_tokens=advancing_estimate)
        self.assertEqual([x["timeout_seconds"] for x in provider.calls], [60, 60, 32])
        self.assertIs(result.error.code, RunFailureCode.MODEL_TIMEOUT)
        self.assertIsNone(result.proposal)
        self.assertEqual(result.attempt_count, 3)
        self.assertEqual(result.usage.total_tokens, 45)
        self.assertIs(result.diagnostics[-1].error_code, RunFailureCode.MODEL_TIMEOUT)

    async def test_late_attempt_with_live_run_deadline_is_still_timeout(self):
        clock = Clock()

        def too_late():
            clock.now += 61
            return ProviderResponse(CANDIDATE, USAGE)

        provider = SequenceProvider(too_late)
        result = await self.run_plan(provider, clock=clock)
        self.assertIs(result.kind, ProposalKind.FAILED)
        self.assertIs(result.error.code, RunFailureCode.MODEL_TIMEOUT)
        self.assertEqual(result.attempt_count, 1)
        self.assertEqual(result.usage, USAGE)
        self.assertEqual(result.diagnostics[0].elapsed_seconds, 61)
        self.assertIsNone(result.proposal)

    async def test_local_processing_deadline_blocks_initial_or_final_result(self):
        clock = Clock()
        def consuming_estimator(_):
            clock.now += 180
            return 100

        provider = SequenceProvider()
        failed = await self.run_plan(provider, clock=clock, estimate_input_tokens=consuming_estimator)
        self.assertIs(failed.error.code, RunFailureCode.MODEL_TIMEOUT)
        self.assertEqual(failed.attempt_count, 0)
        self.assertEqual(provider.calls, [])

    async def test_known_usage_below_reservation_releases_budget(self):
        provider = SequenceProvider(ProviderResponse("bad", USAGE), ProviderResponse(CANDIDATE, USAGE))
        result = await self.run_plan(provider, estimate_input_tokens=lambda _: 25_000)
        self.assertIs(result.kind, ProposalKind.CANDIDATE)
        self.assertEqual(result.usage.total_tokens, 30)
        self.assertEqual(result.diagnostics[0].reserved_tokens, 25_000 + MAX_OUTPUT_TOKENS)
        self.assertEqual(result.diagnostics[0].accounted_tokens, 15)

    async def test_partial_usage_reserves_tokens_and_preserves_unknown_actuals(self):
        provider = SequenceProvider(
            ProviderResponse("bad", TokenUsage(prompt_tokens=6500)),
            ProviderResponse(CANDIDATE, USAGE),
        )
        result = await self.run_plan(provider, estimate_input_tokens=lambda _: 13_000)
        self.assertIs(result.error.code, RunFailureCode.MODEL_BUDGET)
        self.assertEqual(result.attempt_count, 1)
        self.assertEqual(result.usage, TokenUsage(prompt_tokens=6500))
        attempt = result.diagnostics[0]
        self.assertEqual(attempt.reserved_tokens, 13_000 + MAX_OUTPUT_TOKENS)
        self.assertEqual(attempt.accounted_tokens, attempt.reserved_tokens)
        self.assertTrue(attempt.usage_unknown)

    async def test_overspent_actual_usage_is_not_clamped_or_continued(self):
        for usage in (
            TokenUsage(prompt_tokens=40_000, completion_tokens=2, total_tokens=40_002),
            TokenUsage(total_tokens=40_002),
        ):
            provider = SequenceProvider(ProviderResponse(CANDIDATE, usage), ProviderResponse(CANDIDATE, USAGE))
            result = await self.run_plan(provider)
            self.assertIs(result.error.code, RunFailureCode.MODEL_BUDGET)
            self.assertEqual(result.attempt_count, 1)
            self.assertEqual(result.usage, usage)
            self.assertEqual(result.diagnostics[0].accounted_tokens, usage.total_tokens)

    async def test_input_budget_and_model_context_fail_before_call(self):
        cases = (
            (SequenceProvider(), lambda _: TOKEN_RESERVE_PER_RUN),
            (SequenceProvider(limits=ModelLimits(context_tokens=9000, max_output_tokens=8192)), lambda _: 1000),
        )
        for provider, estimate in cases:
            result = await self.run_plan(provider, estimate_input_tokens=estimate)
            self.assertIs(result.error.code, RunFailureCode.MODEL_BUDGET)
            self.assertEqual(result.attempt_count, 0)
            self.assertEqual(provider.calls, [])

    async def test_model_output_cap_and_default_estimate_include_the_wire_prompt(self):
        provider = SequenceProvider(
            ProviderResponse(CANDIDATE, USAGE),
            limits=ModelLimits(context_tokens=120_000, max_output_tokens=2048),
        )
        result = await generate_proposal(
            spec=pm_support.spec_revision(), config=pm_support.config(),
            mode=PlanningMode.REAL, provider=provider,
        )
        self.assertIs(result.kind, ProposalKind.CANDIDATE)
        self.assertEqual(provider.calls[0]["max_tokens"], 2048)
        self.assertGreater(result.diagnostics[0].reserved_tokens, MAX_OUTPUT_TOKENS + 1000)

    async def test_model_not_in_allowlist_and_invalid_estimate_make_no_request(self):
        provider = SequenceProvider()
        model = await self.run_plan(provider, config=pm_support.config(model="unapproved"))
        tokens = await self.run_plan(provider, estimate_input_tokens=lambda _: True)
        for result in (model, tokens):
            self.assertIs(result.error.code, RunFailureCode.INTERNAL_ERROR)
            self.assertEqual(result.attempt_count, 0)
        self.assertEqual(provider.calls, [])

    async def test_cancelled_planning_releases_active_request_without_retry(self):
        started = asyncio.Event()
        released = asyncio.Event()

        class WaitingProvider(SequenceProvider):
            async def complete_json(self, **options):
                self.calls.append(options)
                started.set()
                try:
                    await asyncio.Future()
                finally:
                    released.set()

        provider = WaitingProvider()
        task = asyncio.create_task(self.run_plan(provider))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(released.is_set())
        self.assertEqual(len(provider.calls), 1)

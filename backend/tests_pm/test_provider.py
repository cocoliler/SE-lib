"""使用本地 HTTP 模拟传输验证单请求适配及显式 fixture。"""

import asyncio
import json
import unittest

import httpx
import pm_support
from flowstudio_contracts import PlanningMode, TokenUsage
from flowstudio_pm import generate_validated_proposal
from flowstudio_pm.providers.deepseek import DeepSeekProvider
from flowstudio_pm.providers.fixture import TestFixtureProvider
from flowstudio_pm.types import ModelLimits, ProviderFailure, ProviderFailureKind, ProviderResponse


MODEL = "test-model"
LIMITS = ModelLimits(context_tokens=30_000, max_output_tokens=8192)
MESSAGES = ({"role": "system", "content": "Return JSON"}, {"role": "user", "content": "{}"})
DUMMY_KEY = "dummy-not-a-provider-credential"


def response_body(content="{}", *, finish="stop", usage=None):
    return {
        "id": "response-42",
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": usage,
    }


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, handler):
        return DeepSeekProvider(
            api_key=DUMMY_KEY, allowed_models={MODEL: LIMITS}, transport=httpx.MockTransport(handler)
        )

    async def complete(self, provider, **changes):
        return await provider.complete_json(
            **{"messages": MESSAGES, "model": MODEL, "max_tokens": 8192, "timeout_seconds": 8, **changes}
        )

    async def test_deepseek_protocol_and_usage(self):
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(
                200,
                headers={"x-request-id": "request-23"},
                json=response_body(" ", finish="length", usage={"prompt_tokens": 12, "completion_tokens": 2, "total_tokens": 14}),
            )

        async with self.provider(handle) as provider:
            result = await self.complete(provider)
            self.assertIs(provider.mode, PlanningMode.REAL)
            self.assertEqual(provider.model_limits(MODEL), LIMITS)
            self.assertNotIn(DUMMY_KEY, repr(provider))
        request, = requests
        self.assertEqual(request.method, "POST")
        self.assertEqual(str(request.url), "https://api.deepseek.com/chat/completions")
        self.assertEqual(request.headers["Authorization"], f"Bearer {DUMMY_KEY}")
        self.assertEqual(request.extensions["timeout"]["read"], 8)
        data = json.loads(request.content)
        self.assertEqual(data["response_format"], {"type": "json_object"})
        self.assertEqual(data["messages"], list(MESSAGES))
        self.assertEqual(data["model"], MODEL)
        self.assertEqual(data["max_tokens"], 8192)
        self.assertIs(data["stream"], False)
        self.assertEqual(result.content, " ")
        self.assertEqual(result.finish_reason, "length")
        self.assertEqual(result.request_id, "request-23")
        self.assertEqual(result.usage, TokenUsage(prompt_tokens=12, completion_tokens=2, total_tokens=14))

    async def test_http_errors_are_normalized_without_retry_redirect_or_raw_body(self):
        for status, kind in (
            (401, ProviderFailureKind.AUTH),
            (403, ProviderFailureKind.AUTH),
            (429, ProviderFailureKind.RATE_LIMIT),
            (500, ProviderFailureKind.TRANSIENT_SERVER),
            (503, ProviderFailureKind.TRANSIENT_SERVER),
            (400, ProviderFailureKind.INVALID_RESPONSE),
            (307, ProviderFailureKind.INVALID_RESPONSE),
        ):
            request_paths = []

            def handle(request):
                request_paths.append(request.url.path)
                return httpx.Response(status, content=DUMMY_KEY, headers={
                    "location": "https://example.com/sensitive",
                    "x-request-id": DUMMY_KEY,
                })

            with self.subTest(status=status):
                async with self.provider(handle) as provider:
                    with self.assertRaises(ProviderFailure) as caught:
                        await self.complete(provider)
                self.assertIs(caught.exception.kind, kind)
                self.assertIsNone(caught.exception.request_id)
                self.assertNotIn(DUMMY_KEY, str(caught.exception))
                self.assertNotIn(DUMMY_KEY, repr(caught.exception))
                self.assertNotIn(DUMMY_KEY, repr(caught.exception.__context__))
                self.assertEqual(request_paths, ["/chat/completions"])

    async def test_network_and_httpx_timeout_are_normalized(self):
        for error, kind in (
            (httpx.ConnectError(DUMMY_KEY), ProviderFailureKind.NETWORK),
            (httpx.ReadTimeout(DUMMY_KEY), ProviderFailureKind.TIMEOUT),
        ):
            def handle(_):
                raise error

            with self.subTest(kind=kind), self.assertRaises(ProviderFailure) as caught:
                async with self.provider(handle) as provider:
                    await self.complete(provider)
            self.assertIs(caught.exception.kind, kind)
            self.assertNotIn(DUMMY_KEY, str(caught.exception))
            self.assertIsNone(caught.exception.__context__)

    async def test_invalid_envelope_still_exposes_valid_usage(self):
        def handle(_):
            return httpx.Response(200, json={"choices": [], "usage": {"total_tokens": 42}})

        async with self.provider(handle) as provider:
            with self.assertRaises(ProviderFailure) as caught:
                await self.complete(provider)
        self.assertIs(caught.exception.kind, ProviderFailureKind.INVALID_RESPONSE)
        self.assertEqual(caught.exception.usage, TokenUsage(total_tokens=42))

    async def test_invalid_or_filtered_finish_cannot_yield_a_candidate(self):
        for finish in (None, "missing", "unrecognized", [], "content_filter", "tool_calls"):
            reply = response_body(finish=finish, usage={"total_tokens": 42})
            if finish == "missing":
                del reply["choices"][0]["finish_reason"]

            with self.subTest(finish=finish):
                async with self.provider(lambda _: httpx.Response(200, json=reply)) as provider:
                    with self.assertRaises(ProviderFailure) as caught:
                        await self.complete(provider)
                self.assertIs(caught.exception.kind, ProviderFailureKind.INVALID_RESPONSE)
                self.assertEqual(caught.exception.usage, TokenUsage(total_tokens=42))
                self.assertEqual(caught.exception.request_id, "response-42")

    async def test_temporary_finish_uses_the_shared_one_retry_budget(self):
        for first, second in (
            ("aborted", "insufficient_system_resource"),
            ("insufficient_system_resource", "aborted"),
        ):
            replies = iter((first, second))
            calls = []
            delays = []

            def handle(_):
                calls.append(next(replies))
                return httpx.Response(200, json=response_body(
                    pm_support.example("task-proposal"),
                    finish=calls[-1],
                    usage={"total_tokens": 42},
                ))

            async def record_delay(seconds):
                delays.append(seconds)

            with self.subTest(first=first):
                async with self.provider(handle) as provider:
                    result = await generate_validated_proposal(
                        pm_support.spec_revision(), pm_support.config(), PlanningMode.REAL,
                        provider, sleep=record_delay, estimate_input_tokens=lambda _: 1,
                    )
                self.assertEqual(calls, [first, second])
                self.assertEqual(len(delays), 1)
                self.assertEqual(result.kind.value, "FAILED")
                self.assertEqual(result.usage, TokenUsage(total_tokens=84))
                self.assertEqual(
                    [(item.provider_failure, item.finish_reason, item.provider_request_id) for item in result.diagnostics],
                    [(ProviderFailureKind.TRANSIENT_SERVER, finish, "response-42") for finish in calls],
                )

    async def test_rejects_literal_and_decoded_credential_echoes(self):
        escaped_key = r"\u0064" + DUMMY_KEY[1:]
        for content in (
            json.dumps({"nested": [{"field": DUMMY_KEY}]}),
            '{"nested":[{"field":"' + escaped_key + '"}]}',
            '{"nested":[{"' + escaped_key + '":1}]}',
            '[' * 1500 + '"' + escaped_key + '"' + ']' * 1500,
            '{"unfinished":"' + escaped_key + '",',
        ):
            with self.subTest(length=len(content)):
                def handle(_):
                    return httpx.Response(200, json=response_body(content, usage={"total_tokens": 42}))

                async with self.provider(handle) as provider:
                    with self.assertRaises(ProviderFailure) as caught:
                        await self.complete(provider)
                self.assertIs(caught.exception.kind, ProviderFailureKind.INVALID_RESPONSE)
                self.assertEqual(caught.exception.usage, TokenUsage(total_tokens=42))
                self.assertIsNone(getattr(caught.exception, "content", None))
                self.assertNotIn(DUMMY_KEY, repr(caught.exception))
                self.assertIsNone(caught.exception.__context__)

    async def test_credential_echo_is_removed_before_length_reaches_parser(self):
        for content in (DUMMY_KEY, '"' + r"\u0064" + DUMMY_KEY[1:] + '"'):
            with self.subTest(content_length=len(content)):
                async with self.provider(lambda _: httpx.Response(200, json=response_body(
                    content, finish="length", usage={"total_tokens": 42},
                ))) as provider:
                    try:
                        response = await self.complete(provider)
                    except ProviderFailure as error:
                        self.fail(f"截断仍需由解析器处理，Provider 返回了 {error.kind}")
                self.assertIsNone(response.content)
                self.assertEqual(response.finish_reason, "length")
                self.assertEqual(response.usage, TokenUsage(total_tokens=42))
                self.assertEqual(response.request_id, "response-42")

    async def test_partial_usage_and_missing_choice_content_are_preserved(self):
        def handle(_):
            return httpx.Response(200, json=response_body(None, usage={"prompt_tokens": 9, "provider_extension": 100}))

        async with self.provider(handle) as provider:
            result = await self.complete(provider)
        self.assertIsNone(result.content)
        self.assertEqual(result.usage, TokenUsage(prompt_tokens=9))
        self.assertEqual(result.request_id, "response-42")

    async def test_malformed_and_contradictory_usage_preserve_the_larger_known_cost(self):
        for raw_usage, expected in (
            (
                {"prompt_tokens": "incorrect", "completion_tokens": 8192, "total_tokens": 41_000},
                TokenUsage(completion_tokens=8192, total_tokens=41_000),
            ),
            (
                {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 41_000},
                TokenUsage(total_tokens=41_000),
            ),
            (
                {"prompt_tokens": 40_000, "completion_tokens": 20, "total_tokens": 2},
                TokenUsage(prompt_tokens=40_000, completion_tokens=20),
            ),
        ):
            def handle(_):
                return httpx.Response(200, json=response_body(usage=raw_usage))

            with self.subTest(raw_usage=raw_usage):
                async with self.provider(handle) as provider:
                    result = await self.complete(provider)
                self.assertEqual(result.usage, expected)

    async def test_invalid_parameters_are_rejected_before_request(self):
        async with self.provider(lambda _: self.fail("invalid request touched transport")) as provider:
            for overrides in (
                {"model": "not-allowed"}, {"max_tokens": 0}, {"max_tokens": 8193},
                {"max_tokens": True}, {"timeout_seconds": float("nan")},
                {"timeout_seconds": 0}, {"timeout_seconds": 61}, {"timeout_seconds": True},
            ):
                with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                    await self.complete(provider, **overrides)
        for config in ({"context_tokens": 0, "max_output_tokens": 1}, {"context_tokens": 3, "max_output_tokens": 4}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                ModelLimits(**config)

    async def test_async_transport_is_cancelled_and_owned_client_closes(self):
        started = asyncio.Event()
        finished = asyncio.Event()

        class Transport(httpx.MockTransport):
            closed = False

            async def aclose(self):
                self.closed = True

        async def handle(_):
            started.set()
            try:
                await asyncio.Future()
            finally:
                finished.set()

        transport = Transport(handle)
        async with DeepSeekProvider(api_key=DUMMY_KEY, allowed_models={MODEL: LIMITS}, transport=transport) as provider:
            task = asyncio.create_task(self.complete(provider))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(finished.is_set())
        self.assertTrue(transport.closed)


class FixtureTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_fixture_selects_response_and_provenance(self):
        fixtures = {
            "candidate": ProviderResponse(pm_support.example("task-proposal")),
            "blocked": ProviderResponse(pm_support.example("task-proposal-blocked")),
        }
        provider = TestFixtureProvider(fixture_id="blocked", fixtures=fixtures)
        result = await provider.complete_json(
            messages=MESSAGES, model=MODEL, max_tokens=8192, timeout_seconds=8
        )
        self.assertIs(provider.mode, PlanningMode.TEST)
        self.assertEqual(provider.fixture_id, "blocked")
        self.assertEqual(result.content, pm_support.example("task-proposal-blocked"))
        self.assertIsNone(result.usage)

    def test_unknown_or_invalid_fixture_id_is_rejected(self):
        for fixture_id in ("unknown", "", None):
            with self.subTest(fixture_id=fixture_id), self.assertRaises(ValueError):
                TestFixtureProvider(fixture_id=fixture_id, fixtures={"candidate": ProviderResponse("{}")})

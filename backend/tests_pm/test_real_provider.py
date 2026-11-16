"""真实入口默认跳过。其余测试仅使用显式标记的模拟 HTTP 传输。"""

import asyncio
import contextlib
import hashlib
import importlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import pm_support
from flowstudio_contracts import sha256_hex
from flowstudio_pm.prompt import build_prompt
from test_planner import BLOCKED, CANDIDATE
from test_provider import DUMMY_KEY, LIMITS, MODEL, response_body
from test_validated_planner import missing_dependency, oversized_candidate

_MODULE = "flowstudio_pm.real_validation"
_ENABLE_ENV = "FLOWSTUDIO_PM_ENABLE_REAL_VALIDATION"
_KEY_ENV = "FLOWSTUDIO_PM_TEST_DUMMY_KEY"


class RealValidationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=pm_support.ROOT.parent)
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.spec_path = self.folder / "spec.json"
        self.config_path = self.folder / "config.json"
        self.evidence_path = self.folder / "evidence.json"
        self.spec = pm_support.spec_revision()
        self.config = pm_support.config()
        self.spec_path.write_text(self.spec.to_json(), encoding="utf-8")
        self.config_path.write_text(self.config.to_json(), encoding="utf-8")

    def cli_args(self, evidence_path=None):
        return [
            "--enable-real", "--spec", str(self.spec_path), "--config", str(self.config_path),
            "--context-tokens", str(LIMITS.context_tokens), "--max-output-tokens", str(LIMITS.max_output_tokens),
            "--api-key-env", _KEY_ENV, "--evidence", str(evidence_path or self.evidence_path),
        ]

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec(_MODULE), "缺少默认关闭的真实验收入口")
        return importlib.import_module(_MODULE)

    def invoke(self, args, *, key=None, read_key=False, reaches_provider=False):
        module = self.module()
        capture = io.StringIO()
        with (
            patch.object(module, "getenv", return_value=key) as credential,
            patch.object(module, "DeepSeekProvider", side_effect=ValueError("敏感输入 " + DUMMY_KEY)) as provider,
            contextlib.redirect_stderr(capture),
            contextlib.redirect_stdout(capture),
        ):
            code = module.main(args)
        if read_key:
            credential.assert_called_once_with(_KEY_ENV)
        else:
            credential.assert_not_called()
        if reaches_provider:
            provider.assert_called_once()
        else:
            provider.assert_not_called()
        self.assertNotIn(DUMMY_KEY, capture.getvalue())
        self.assertNotIn("敏感输入", capture.getvalue())
        return code, capture.getvalue()

    def test_cli_disabled_does_not_read_credential_or_create_provider(self):
        code, output = self.invoke(self.cli_args()[1:])
        self.assertEqual(code, 2)
        self.assertIn("--enable-real", output)
        self.assertFalse(self.evidence_path.exists())

    def test_enabled_with_missing_arguments_or_credential_fails(self):
        for args, read_key in ((["--enable-real"], False), (self.cli_args(), True)):
            with self.subTest(read_key=read_key):
                code, output = self.invoke(args, read_key=read_key)
                self.assertEqual(code, 2)
                self.assertIn("缺少", output)
        self.assertFalse(self.evidence_path.exists())

    def test_strict_inputs_and_stale_spec_hash_fail_before_credentials(self):
        for path, value in (
            (self.spec_path, {"revision": "1"}),
            (self.spec_path, {"hash": "0" * 64}),
            (self.config_path, {"unexpected": "敏感输入"}),
        ):
            with self.subTest(value=value):
                original = path.read_text(encoding="utf-8")
                path.write_text(json.dumps({**json.loads(original), **value}), encoding="utf-8")
                try:
                    code, _ = self.invoke(self.cli_args())
                    self.assertEqual(code, 2)
                    self.assertFalse(self.evidence_path.exists())
                finally:
                    path.write_text(original, encoding="utf-8")
        args = self.cli_args()
        args[args.index("--context-tokens") + 1] = "0"
        self.assertEqual(self.invoke(args)[0], 2)

    def test_invalid_evidence_paths_fail_before_credentials(self):
        worktree = self.folder / "simulated-worktree"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        junction = self.folder / "linked-worktree"
        if os.name == "nt":
            subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(worktree)],
                           check=True, capture_output=True)
        else:
            junction.symlink_to(worktree, target_is_directory=True)

        for destination in (
            self.folder / "missing-parent" / "evidence.json",
            pm_support.BACKEND / "evidence.json",
            worktree / "evidence.json",
            junction / "evidence.json",
        ):
            with self.subTest(destination=destination):
                code, _ = self.invoke(self.cli_args(destination))
                self.assertEqual(code, 2)
                self.assertFalse(destination.exists())

    def test_existing_evidence_is_preserved(self):
        self.evidence_path.write_text("previous", encoding="utf-8")
        code, _ = self.invoke(self.cli_args())
        self.assertEqual(code, 2)
        self.assertEqual(self.evidence_path.read_text(encoding="utf-8"), "previous")

    def test_credential_in_input_is_rejected_before_provider_creation(self):
        spec = pm_support.spec_revision(background=DUMMY_KEY)
        self.spec_path.write_text(spec.to_json(), encoding="utf-8")
        code, _ = self.invoke(self.cli_args(), key=DUMMY_KEY, read_key=True)
        self.assertEqual(code, 2)
        self.assertFalse(self.evidence_path.exists())

    def test_provider_setup_error_does_not_echo_credential_or_input(self):
        code, _ = self.invoke(self.cli_args(), key=DUMMY_KEY, read_key=True, reaches_provider=True)
        self.assertEqual(code, 2)
        self.assertFalse(self.evidence_path.exists())

    def simulate(self, *replies):
        module = self.module()
        pending = iter(replies)
        requests = []

        class Transport(httpx.MockTransport):
            closed = False

            async def aclose(self):
                self.closed = True

        def handle(request):
            requests.append(json.loads(request.content))
            content, finish = next(pending)
            body = response_body(
                content, finish=finish, usage={"prompt_tokens": 31, "completion_tokens": 11, "total_tokens": 42},
            )
            body["choices"][0]["message"]["reasoning_content"] = "hidden " + DUMMY_KEY
            return httpx.Response(200, headers={"x-request-id": f"request-{len(requests)}"}, json=body)

        transport = Transport(handle)
        provider = module.DeepSeekProvider(api_key=DUMMY_KEY, allowed_models={MODEL: LIMITS}, transport=transport)
        code = asyncio.run(module._write_validation_evidence(
            self.spec, self.config, LIMITS, self.evidence_path, provider,
            api_key=DUMMY_KEY, evidence_source="simulated_transport",
        ))
        self.assertTrue(transport.closed)
        self.assertEqual(len(requests), len(replies))
        saved = self.evidence_path.read_text(encoding="utf-8")
        self.assertNotIn(DUMMY_KEY, saved)
        self.assertNotIn("reasoning_content", saved)
        self.assertNotIn("Authorization", saved)
        return code, json.loads(saved), requests

    def test_simulated_candidate_records_raw_content_and_real_d_report(self):
        code, evidence, requests = self.simulate((CANDIDATE, "stop"))
        self.assertEqual(code, 0)
        self.assertEqual(evidence["evidence_source"], "simulated_transport")
        self.assertEqual(evidence["mode"], "REAL")
        self.assertEqual(evidence["human_review"], "pending")
        self.assertEqual(evidence["outcome"], "CANDIDATE")
        self.assertEqual(evidence["spec_revision"], json.loads(self.spec.to_json()))
        self.assertEqual(evidence["planning_config"], json.loads(self.config.to_json()))
        self.assertEqual(evidence["input_hash"], sha256_hex({
            "spec_revision": evidence["spec_revision"], "planning_config": evidence["planning_config"],
        }))
        self.assertEqual(evidence["model"], MODEL)
        self.assertEqual(evidence["model_limits"], {"context_tokens": 30_000, "max_output_tokens": 8192})
        self.assertEqual(evidence["usage"]["total_tokens"], 42)
        self.assertEqual(evidence["graph_check"], evidence["latest_report_check"])
        self.assertEqual(evidence["graph_check"]["proposal"], evidence["proposal"])
        self.assertTrue(evidence["graph_check"]["report"]["valid"])
        attempt, = evidence["attempts"]
        self.assertEqual(attempt["content"], CANDIDATE)
        self.assertEqual(attempt["response_hash"], hashlib.sha256(CANDIDATE.encode("utf-8")).hexdigest())
        self.assertEqual(attempt["finish_reason"], "stop")
        self.assertEqual(attempt["provider_request_id"], "request-1")
        self.assertEqual(attempt["actual_usage"]["total_tokens"], 42)
        prompt = build_prompt(self.spec, self.config, validate_graph=True)
        self.assertEqual(evidence["initial_prompt"], {"version": prompt.version, "hash": prompt.hash})
        self.assertEqual(attempt["prompt_hash"], sha256_hex({
            "version": attempt["prompt_version"], "messages": requests[0]["messages"],
        }))

    def test_failed_graph_records_latest_report_separately_from_size_rejection(self):
        invalid = json.dumps(missing_dependency())
        oversized = json.dumps(oversized_candidate())
        code, evidence, _ = self.simulate((invalid, "stop"), (invalid, "stop"), (oversized, "stop"))
        self.assertEqual(code, 1)
        self.assertEqual(evidence["outcome"], "FAILED")
        self.assertEqual(evidence["graph_failure"], "GRAPH_LIMIT")
        self.assertEqual(evidence["usage"]["total_tokens"], 126)
        self.assertIsNone(evidence["proposal"])
        self.assertEqual(evidence["graph_check"]["attempt_index"], 3)
        self.assertIsNone(evidence["graph_check"]["report"])
        self.assertEqual(evidence["graph_check"]["limit"], {"limit": 1000, "actual": 1035})
        latest = evidence["latest_report_check"]
        self.assertEqual(latest["attempt_index"], 2)
        self.assertFalse(latest["report"]["valid"])
        self.assertEqual(latest["proposal"]["tasks"][1]["dependencies"][-1], "T-Missing")

    def test_failed_model_retains_safe_content_but_discards_credential_echo(self):
        escaped_key = r"\u0064" + DUMMY_KEY[1:]
        cases = (("{}", "content_filter", "{}"), ('{"field":"' + escaped_key + '"}', "stop", None))
        for content, finish, expected in cases:
            with self.subTest(finish=finish):
                self.evidence_path = self.folder / f"evidence-{finish}.json"
                code, evidence, _ = self.simulate((content, finish))
                self.assertEqual(code, 1)
                self.assertEqual(evidence["outcome"], "FAILED")
                self.assertEqual(evidence["error"]["code"], "MODEL_SCHEMA")
                attempt, = evidence["attempts"]
                self.assertEqual(attempt["content"], expected)
                self.assertNotIn(escaped_key, self.evidence_path.read_text(encoding="utf-8"))
                self.assertEqual(attempt["finish_reason"], finish)
                self.assertEqual(attempt["actual_usage"]["total_tokens"], 42)

    def test_needs_input_exit_is_nonzero(self):
        code, evidence, _ = self.simulate((BLOCKED, "stop"))
        self.assertEqual(code, 1)
        self.assertEqual(evidence["outcome"], "NEEDS_INPUT")
        self.assertTrue(evidence["proposal"]["blocking_questions"])
        self.assertIsNone(evidence["graph_check"])
        self.assertEqual(evidence["human_review"], "pending")


class GuardedRealProviderTest(unittest.TestCase):
    @unittest.skipUnless(os.getenv(_ENABLE_ENV) == "1", f"未显式启用 {_ENABLE_ENV}=1")
    def test_explicit_deepseek_validation_has_a_technical_candidate(self):
        from flowstudio_pm.real_validation import main

        args = ["--enable-real"]
        for option in ("spec", "config", "context-tokens", "max-output-tokens", "api-key-env", "evidence"):
            value = os.getenv("FLOWSTUDIO_PM_REAL_" + option.replace("-", "_").upper())
            self.assertTrue(value, f"真实验收缺少 {option} 配置")
            args.extend((f"--{option}", value))
        self.assertEqual(main(args), 0, "真实验收未得到技术候选，诊断见指定证据")

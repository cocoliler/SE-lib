"""引擎验收：官方样例对齐、hash 绑定、确定性以及报告与派生的关系。"""

from __future__ import annotations

import support  # noqa: F401  先完成路径引导

import re
import unittest

from flowstudio_contracts.samples import sample_derivation, sample_design_spec, sample_tasks
from flowstudio_orchestration import (
    RULES,
    build_plan,
    compute_coverage,
    compute_input_hash,
    evaluate,
    validate_workflow,
)
from support import policy, requirement, spec, task


class SampleParityTest(unittest.TestCase):
    def test_official_sample_matches_expected_derivation(self) -> None:
        derivation = build_plan(sample_tasks(), sample_design_spec())
        expected = sample_derivation()

        self.assertTrue(derivation.validation_report.valid)
        self.assertEqual(derivation.edges, expected.edges)
        self.assertEqual(derivation.execution_stages, expected.execution_stages)
        self.assertEqual(derivation.parallel_batches, expected.parallel_batches)
        self.assertEqual(derivation.ordered_task_ids, expected.ordered_task_ids)
        self.assertEqual(derivation.validation_report.coverage, expected.validation_report.coverage)
        self.assertEqual(derivation.validation_report.errors, [])
        self.assertEqual(derivation.validation_report.warnings, [])

    def test_sample_hash_binds_tasks_not_only_spec(self) -> None:
        """契约样例的 input_hash 只散列规格；引擎按设计绑定任务与约束，故两者不同。"""
        derivation = build_plan(sample_tasks(), sample_design_spec())
        self.assertNotEqual(derivation.input_hash, sample_derivation().input_hash)
        self.assertRegex(derivation.input_hash, re.compile(r"^[0-9a-f]{64}$"))
        self.assertEqual(derivation.input_hash, derivation.validation_report.input_hash)


class HashTest(unittest.TestCase):
    def test_same_input_same_hash(self) -> None:
        tasks = [task("A", requirements=("R-01",))]
        self.assertEqual(
            compute_input_hash(tasks, spec("R-01"), None),
            compute_input_hash(tasks, spec("R-01"), None),
        )

    def test_task_change_changes_hash(self) -> None:
        base = [task("A", requirements=("R-01",))]
        renamed = [task("A", requirements=("R-01",), name="改名后的任务")]
        content = spec("R-01")

        self.assertNotEqual(
            compute_input_hash(base, content, None),
            compute_input_hash(renamed, content, None),
        )

    def test_policy_change_changes_hash_but_not_derivation(self) -> None:
        tasks = [task("A", requirements=("R-01",))]
        content = spec("R-01")
        unconstrained = policy()
        restrictive = policy(stages=["build"])

        plain = build_plan(tasks, content)
        with_policy = build_plan(tasks, content, unconstrained)
        restricted = build_plan(tasks, content, restrictive)

        self.assertNotEqual(plain.input_hash, with_policy.input_hash)
        self.assertEqual(plain.parallel_batches, with_policy.parallel_batches)
        self.assertEqual(plain.execution_stages, restricted.execution_stages)
        self.assertTrue(restricted.validation_report.valid)


class ReportTest(unittest.TestCase):
    def test_validate_workflow_reuses_the_same_implementation(self) -> None:
        tasks = sample_tasks()
        content = sample_design_spec()
        derivation = build_plan(tasks, content)
        report = validate_workflow(tasks, content)

        self.assertEqual(report.model_dump(mode="json"), derivation.validation_report.model_dump(mode="json"))

    def test_invalid_input_returns_empty_derivation_with_matching_report(self) -> None:
        tasks = [task("A", requirements=("R-99",))]
        content = spec("R-01")
        derivation = build_plan(tasks, content)
        report, raw = evaluate(tasks, content, None)

        self.assertFalse(derivation.validation_report.valid)
        self.assertEqual(derivation.edges, [])
        self.assertEqual(derivation.execution_stages, [])
        self.assertEqual(derivation.parallel_batches, [])
        self.assertEqual(derivation.ordered_task_ids, [])
        self.assertEqual(derivation.input_hash, report.input_hash)
        self.assertIsNone(raw)

    def test_warnings_do_not_invalidate_report(self) -> None:
        tasks = [
            task("A", requirements=("R-01",), name="Build API"),
            task("B", name="build api"),
        ]
        report = validate_workflow(tasks, spec("R-01"))
        self.assertTrue(report.valid)
        self.assertEqual(len(report.warnings), 1)
        self.assertEqual(report.errors, [])

    def test_report_is_deterministic(self) -> None:
        tasks = sample_tasks()
        content = sample_design_spec()
        self.assertEqual(build_plan(tasks, content).to_json(), build_plan(tasks, content).to_json())

    def test_coverage_follows_spec_order(self) -> None:
        content = spec(
            requirement("R-02"),
            requirement("R-01"),
        )
        tasks = [task("A", requirements=("R-01",))]
        coverage = compute_coverage(tasks, content)

        self.assertEqual(coverage.covered_ids, ["R-01"])
        self.assertEqual(coverage.uncovered_ids, ["R-02"])


class RegistryTest(unittest.TestCase):
    def test_every_rule_has_unique_id_and_version(self) -> None:
        identifiers = [rule.rule_id for rule in RULES]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertTrue(all(rule.version == "1.0" for rule in RULES))

    def test_plan_derivation_exposes_stage_and_batch_semantics(self) -> None:
        tasks = [
            task("A", requirements=("R-01",), stage="discovery"),
            task("B", stage="design", dependencies=("A",)),
            task("C", stage="design", dependencies=("A",)),
        ]
        derivation = build_plan(tasks, spec("R-01"))

        self.assertEqual(derivation.parallel_batches, [["A"], ["B", "C"]])
        self.assertEqual(
            [(stage.stage_id, stage.task_ids) for stage in derivation.execution_stages],
            [("discovery", ["A"]), ("design", ["B", "C"])],
        )


if __name__ == "__main__":
    unittest.main()

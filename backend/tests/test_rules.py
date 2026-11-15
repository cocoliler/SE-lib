"""规则验收：结构、引用、策略约束、覆盖与只读告警（A05/A06）。"""

from __future__ import annotations

import support  # noqa: F401  先完成路径引导

import unittest

from flowstudio_contracts import AssumptionImpact, IssueCode, RequirementPriority
from flowstudio_contracts.tasks import Deliverable
from flowstudio_orchestration import (
    OrchestrationInputError,
    OrchestrationLimitError,
    build_plan,
    validate_workflow,
)
from support import (
    assumption,
    policy,
    requirement,
    spec,
    spec_input,
    stage_edge,
    task,
    task_input,
    unvalidated,
)


def error_codes(report) -> list[str]:
    return [str(item.code) for item in report.errors]


def warning_codes(report) -> list[str]:
    return [str(item.code) for item in report.warnings]


class IdentityRulesTest(unittest.TestCase):
    def test_duplicate_task_id_blocks_before_graph(self) -> None:
        tasks = [task("A", requirements=("R-01",)), task("A")]
        report = validate_workflow(tasks, spec("R-01"))

        self.assertFalse(report.valid)
        self.assertEqual(error_codes(report), ["DUPLICATE_ID"])
        self.assertEqual(report.errors[0].path, "/tasks/1/task_id")
        self.assertEqual(build_plan(tasks, spec("R-01")).parallel_batches, [])

    def test_missing_dependency_reports_exact_pointer(self) -> None:
        tasks = [task("A", requirements=("R-01",)), task("B", dependencies=("X",))]
        report = validate_workflow(tasks, spec("R-01"))

        self.assertEqual(error_codes(report), ["MISSING_DEPENDENCY"])
        self.assertEqual(report.errors[0].path, "/tasks/1/dependencies/0")
        self.assertEqual([(e.source, e.target) for e in report.errors[0].edges], [("X", "B")])

    def test_duplicate_dependency_is_not_silently_deduplicated(self) -> None:
        broken = unvalidated(task("B", dependencies=("A",)), dependencies=["A", "A"])
        report = validate_workflow([task("A", requirements=("R-01",)), broken], spec("R-01"))

        self.assertEqual(error_codes(report), ["DUPLICATE_DEPENDENCY"])
        self.assertEqual(report.errors[0].path, "/tasks/1/dependencies/1")

    def test_input_must_come_from_direct_dependency(self) -> None:
        tasks = [
            task("A", requirements=("R-01",)),
            task("C"),
            task("B", dependencies=("A",), inputs=(task_input("C", "D-C"),)),
        ]
        report = validate_workflow(tasks, spec("R-01"))

        self.assertIn(IssueCode.INPUT_NOT_DEPENDENCY, [item.code for item in report.errors])
        issue = next(item for item in report.errors if item.code is IssueCode.INPUT_NOT_DEPENDENCY)
        self.assertEqual(issue.path, "/tasks/2/inputs/0")
        self.assertEqual(set(issue.task_ids), {"B", "C"})

    def test_input_referencing_unknown_task(self) -> None:
        tasks = [task("A", requirements=("R-01",), inputs=(task_input("X", "D-X"),))]
        report = validate_workflow(tasks, spec("R-01"))
        self.assertEqual(error_codes(report), ["INPUT_NOT_DEPENDENCY"])

    def test_missing_deliverable_on_upstream(self) -> None:
        tasks = [
            task("A", requirements=("R-01",)),
            task("B", dependencies=("A",), inputs=(task_input("A", "D-NOT-THERE"),)),
        ]
        report = validate_workflow(tasks, spec("R-01"))

        self.assertEqual(error_codes(report), ["MISSING_INPUT"])
        self.assertEqual(report.errors[0].path, "/tasks/1/inputs/0/deliverable_id")

    def test_existing_deliverable_passes(self) -> None:
        tasks = [
            task("A", requirements=("R-01",)),
            task("B", dependencies=("A",), inputs=(task_input("A", "D-A"),)),
        ]
        self.assertTrue(validate_workflow(tasks, spec("R-01")).valid)


class RequirementRulesTest(unittest.TestCase):
    def test_unknown_requirement_reference(self) -> None:
        tasks = [task("A", requirements=("R-99",))]
        report = validate_workflow(tasks, spec("R-01"))

        self.assertEqual(error_codes(report), ["UNKNOWN_REQUIREMENT"])
        self.assertEqual(report.errors[0].path, "/tasks/0/source_requirement_ids/0")

    def test_unknown_spec_input_reference(self) -> None:
        tasks = [task("A", requirements=("R-01",), inputs=(spec_input("R-99"),))]
        report = validate_workflow(tasks, spec("R-01"))

        self.assertEqual(error_codes(report), ["UNKNOWN_REQUIREMENT"])
        self.assertEqual(report.errors[0].path, "/tasks/0/inputs/0/requirement_id")

    def test_must_uncovered_blocks_and_is_reported(self) -> None:
        tasks = [task("A", requirements=("R-01",))]
        report = validate_workflow(tasks, spec("R-01", "R-02"))

        self.assertEqual(error_codes(report), ["REQUIRED_UNCOVERED"])
        self.assertEqual(report.errors[0].path, "/requirements/1")
        self.assertEqual(report.coverage.covered_ids, ["R-01"])
        self.assertEqual(report.coverage.uncovered_ids, ["R-02"])

    def test_optional_uncovered_only_appears_in_coverage(self) -> None:
        """契约没有允许 warning 的覆盖错误码，因此不伪造 warning（已知缺口）。"""
        tasks = [task("A", requirements=("R-01",))]
        report = validate_workflow(
            tasks,
            spec(requirement("R-01"), requirement("R-02", RequirementPriority.SHOULD)),
        )

        self.assertTrue(report.valid)
        self.assertEqual(report.coverage.uncovered_ids, ["R-02"])
        self.assertEqual(report.warnings, [])

    def test_required_category(self) -> None:
        tasks = [task("A", requirements=("R-01",))]
        report = validate_workflow(tasks, spec("R-01"), policy(required=("qa",)))

        self.assertEqual(error_codes(report), ["REQUIRED_CATEGORY"])
        self.assertIn("qa", report.errors[0].message)


class PolicyRulesTest(unittest.TestCase):
    def test_stage_role_category_limits(self) -> None:
        tasks = [task("A", requirements=("R-01",), stage="build", role="developer", category="build")]

        stage_report = validate_workflow(tasks, spec("R-01"), policy(stages=["design"]))
        role_report = validate_workflow(tasks, spec("R-01"), policy(roles=["tester"]))
        category_report = validate_workflow(tasks, spec("R-01"), policy(categories=["qa"]))

        self.assertEqual(error_codes(stage_report), ["INVALID_STAGE"])
        self.assertEqual(error_codes(role_report), ["INVALID_ROLE"])
        self.assertEqual(error_codes(category_report), ["INVALID_CATEGORY"])

    def test_empty_allowlist_is_unsatisfiable_not_invalid_stage(self) -> None:
        tasks = [task("A", requirements=("R-01",))]
        report = validate_workflow(tasks, spec("R-01"), policy(stages=[]))

        self.assertEqual(error_codes(report), ["POLICY_UNSATISFIABLE"])
        self.assertEqual(report.errors[0].path, "/policy/allowed_stages")

    def test_cross_stage_dependency_must_match_allowed_edges(self) -> None:
        allowed = policy(stage_edges=[stage_edge("build", "test")])
        forward = [
            task("A", requirements=("R-01",), stage="build"),
            task("B", stage="test", dependencies=("A",)),
        ]
        backward = [
            task("A", requirements=("R-01",), stage="test"),
            task("B", stage="build", dependencies=("A",)),
        ]

        self.assertTrue(validate_workflow(forward, spec("R-01"), allowed).valid)
        report = validate_workflow(backward, spec("R-01"), allowed)
        self.assertEqual(error_codes(report), ["STAGE_EDGE_FORBIDDEN"])
        self.assertEqual(report.errors[0].path, "/tasks/1/dependencies/0")

    def test_same_stage_dependency_is_always_allowed(self) -> None:
        allowed = policy(stage_edges=[stage_edge("build", "test")])
        tasks = [
            task("A", requirements=("R-01",), stage="build"),
            task("B", stage="build", dependencies=("A",)),
        ]
        self.assertTrue(validate_workflow(tasks, spec("R-01"), allowed).valid)

    def test_no_policy_means_no_extra_limits(self) -> None:
        tasks = [
            task("A", requirements=("R-01",), stage="whatever", category="custom", role="whoever"),
        ]
        self.assertTrue(validate_workflow(tasks, spec("R-01")).valid)


class AssumptionRulesTest(unittest.TestCase):
    def test_critical_assumption_blocks(self) -> None:
        tasks = [
            task(
                "A",
                requirements=("R-01",),
                assumptions=(assumption("A-01", impact=AssumptionImpact.CRITICAL),),
            )
        ]
        report = validate_workflow(tasks, spec("R-01"))

        self.assertEqual(error_codes(report), ["CRITICAL_ASSUMPTION"])
        self.assertEqual(report.errors[0].path, "/tasks/0/assumptions/0")

    def test_assumption_ids_are_globally_unique(self) -> None:
        tasks = [
            task("A", requirements=("R-01",), assumptions=(assumption("A-01"),)),
            task("B", dependencies=("A",), assumptions=(assumption("A-01"),)),
        ]
        report = validate_workflow(tasks, spec("R-01"))

        self.assertEqual(error_codes(report), ["DUPLICATE_ID"])
        self.assertEqual(report.errors[0].path, "/tasks/1/assumptions/0/id")

    def test_low_assumption_is_accepted(self) -> None:
        tasks = [task("A", requirements=("R-01",), assumptions=(assumption("A-01"),))]
        self.assertTrue(validate_workflow(tasks, spec("R-01")).valid)


class AdvisoryRulesTest(unittest.TestCase):
    def test_orphan_warning_needs_basis(self) -> None:
        weak = [task("A", rationale="")]
        strong = [task("A", rationale="先固定验收口径")]

        report = validate_workflow(weak, spec(requirement("R-01", RequirementPriority.SHOULD)))
        self.assertTrue(report.valid)
        self.assertEqual(warning_codes(report), ["ORPHAN"])
        self.assertEqual(report.errors, [])

        self.assertEqual(validate_workflow(strong, spec("R-01")).warnings, [])

    def test_requirement_reference_suppresses_orphan(self) -> None:
        report = validate_workflow(
            [task("A", requirements=("R-01",), rationale="")],
            spec("R-01"),
        )
        self.assertEqual(warning_codes(report), [])

    def test_connected_task_is_not_orphan(self) -> None:
        tasks = [task("A", requirements=("R-01",)), task("B", dependencies=("A",), rationale="")]
        self.assertEqual(validate_workflow(tasks, spec("R-01")).warnings, [])

    def test_duplicate_task_name_is_warning_only(self) -> None:
        tasks = [
            task("A", requirements=("R-01",), name="Build API"),
            task("B", name="build   api"),
        ]
        report = validate_workflow(tasks, spec("R-01"))

        self.assertTrue(report.valid)
        self.assertEqual(warning_codes(report), ["POSSIBLE_DUPLICATE"])
        self.assertEqual(set(report.warnings[0].task_ids), {"A", "B"})

    def test_duplicate_deliverable_text_is_warning_only(self) -> None:
        tasks = [
            task("A", requirements=("R-01",), deliverables=[Deliverable(id="D-1", text="同一份交付")]),
            task("B", deliverables=[Deliverable(id="D-2", text="同一份交付")]),
        ]
        report = validate_workflow(tasks, spec("R-01"))

        self.assertTrue(report.valid)
        self.assertEqual(warning_codes(report), ["POSSIBLE_DUPLICATE"])


class LimitTest(unittest.TestCase):
    def test_empty_plan_is_rejected(self) -> None:
        with self.assertRaises(OrchestrationInputError):
            build_plan([], spec("R-01"))

    def test_task_limit(self) -> None:
        tasks = [task(f"T{index:03d}", requirements=("R-01",) if index == 0 else ()) for index in range(101)]
        with self.assertRaises(OrchestrationLimitError) as caught:
            build_plan(tasks, spec("R-01"))
        self.assertEqual(caught.exception.limit, 100)
        self.assertEqual(caught.exception.actual, 101)

    def test_edge_limit_boundary(self) -> None:
        # 45 个稠密任务 = 990 条边；再加 10 条 = 1000 条，正好在上限内。
        tasks = [task(f"T{index:02d}", requirements=("R-01",) if index == 0 else ()) for index in range(45)]
        for index in range(1, 45):
            tasks[index] = task(
                f"T{index:02d}",
                dependencies=tuple(f"T{previous:02d}" for previous in range(index)),
            )
        for index in range(45, 55):
            tasks.append(task(f"T{index:02d}", dependencies=("T00",)))

        self.assertTrue(build_plan(tasks, spec("R-01")).validation_report.valid)

        tasks.append(task("T55", dependencies=("T00",)))
        with self.assertRaises(OrchestrationLimitError) as caught:
            build_plan(tasks, spec("R-01"))
        self.assertEqual(caught.exception.limit, 1000)
        self.assertEqual(caught.exception.actual, 1001)


if __name__ == "__main__":
    unittest.main()

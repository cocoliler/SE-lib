"""图算法验收：拓扑批次、环定位、阶段分组与顺序确定性（A07）。"""

from __future__ import annotations

import support  # noqa: F401  先完成路径引导

import random
import unittest

from flowstudio_orchestration import build_plan, find_cycles, kahn_batches, scan_dependencies
from flowstudio_orchestration.issues import task_path
from support import spec, task


class BatchesTest(unittest.TestCase):
    def test_diamond_uses_layers_not_enqueue_order(self) -> None:
        tasks = [
            task("A", requirements=("R-01",)),
            task("B", dependencies=("A",)),
            task("C", dependencies=("A",)),
            task("D", dependencies=("B", "C")),
        ]
        derivation = build_plan(tasks, spec("R-01"))

        self.assertTrue(derivation.validation_report.valid)
        self.assertEqual(derivation.parallel_batches, [["A"], ["B", "C"], ["D"]])
        self.assertEqual(derivation.ordered_task_ids, ["A", "B", "C", "D"])
        self.assertEqual(
            [(edge.source, edge.target) for edge in derivation.edges],
            [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")],
        )

    def test_multiple_roots_and_independent_components(self) -> None:
        tasks = [
            task("A", requirements=("R-01",)),
            task("B", dependencies=("A",)),
            task("C"),
            task("D", dependencies=("C",)),
        ]
        derivation = build_plan(tasks, spec("R-01"))

        self.assertTrue(derivation.validation_report.valid)
        self.assertEqual(derivation.parallel_batches, [["A", "C"], ["B", "D"]])

    def test_batches_are_stable_regardless_of_input_order(self) -> None:
        tasks = [
            task("A", requirements=("R-01",)),
            task("B", dependencies=("A",)),
            task("C", dependencies=("A",)),
            task("D", dependencies=("B", "C")),
        ]
        forward = build_plan(tasks, spec("R-01"))
        backward = build_plan(list(reversed(tasks)), spec("R-01"))

        self.assertEqual(forward.parallel_batches, backward.parallel_batches)
        self.assertEqual(forward.ordered_task_ids, backward.ordered_task_ids)
        self.assertEqual(forward.edges, backward.edges)
        self.assertEqual(forward.execution_stages, backward.execution_stages)

    def test_single_task_plan_is_legal(self) -> None:
        derivation = build_plan([task("A", requirements=("R-01",))], spec("R-01"))
        self.assertTrue(derivation.validation_report.valid)
        self.assertEqual(derivation.parallel_batches, [["A"]])


class CycleTest(unittest.TestCase):
    def test_reports_actual_cycle_not_downstream(self) -> None:
        tasks = [
            task("A", requirements=("R-01",), dependencies=("C",)),
            task("B", dependencies=("A",)),
            task("C", dependencies=("B",)),
            task("D", dependencies=("C",)),
        ]
        derivation = build_plan(tasks, spec("R-01"))

        self.assertFalse(derivation.validation_report.valid)
        cycles = [item for item in derivation.validation_report.errors if item.code == "CYCLE"]
        self.assertEqual(len(cycles), 1)
        self.assertEqual(set(cycles[0].task_ids), {"A", "B", "C"})
        self.assertNotIn("D", cycles[0].task_ids)
        self.assertEqual(len(cycles[0].edges), 3)
        self.assertEqual(derivation.parallel_batches, [])
        self.assertEqual(derivation.ordered_task_ids, [])

    def test_self_loop_is_structural_error_not_cycle(self) -> None:
        tasks = [task("A", requirements=("R-01",), dependencies=("A",))]
        report = build_plan(tasks, spec("R-01")).validation_report
        self.assertEqual([item.code for item in report.errors], ["SELF_DEPENDENCY"])
        self.assertEqual(report.errors[0].path, "/tasks/0/dependencies/0")

    def test_find_cycles_is_iterative_and_deterministic(self) -> None:
        children = {"A": ("B",), "B": ("C",), "C": ("A",)}
        self.assertEqual(find_cycles(("A", "B", "C"), children), [["A", "B", "C", "A"]])

    def test_cycle_detection_does_not_recurse_on_long_chain(self) -> None:
        # 500 节点链 + 末端回到起点：迭代实现不应触发递归深度限制。
        size = 500
        nodes = [f"T{index:03d}" for index in range(size)]
        children = {node: (nodes[index + 1],) for index, node in enumerate(nodes[:-1])}
        children[nodes[-1]] = (nodes[0],)
        cycles = find_cycles(nodes, children)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(len(cycles[0]), size + 1)


class StageTest(unittest.TestCase):
    def test_stage_order_uses_earliest_layer_then_stage_id(self) -> None:
        tasks = [
            task("A", stage="zeta", requirements=("R-01",)),
            task("B", stage="alpha", dependencies=("A",)),
            task("C", stage="beta", dependencies=("A",)),
        ]
        derivation = build_plan(tasks, spec("R-01"))

        self.assertEqual(
            [(stage.stage_id, stage.task_ids) for stage in derivation.execution_stages],
            [("zeta", ["A"]), ("alpha", ["B"]), ("beta", ["C"])],
        )

    def test_same_stage_can_span_layers(self) -> None:
        tasks = [
            task("A", stage="build", requirements=("R-01",)),
            task("B", stage="build", dependencies=("A",)),
        ]
        derivation = build_plan(tasks, spec("R-01"))
        self.assertEqual(
            [(stage.stage_id, stage.task_ids) for stage in derivation.execution_stages],
            [("build", ["A", "B"])],
        )


class PropertyTest(unittest.TestCase):
    def test_random_dags_keep_edge_order_and_cover_every_task(self) -> None:
        """随机 DAG 性质：每条边满足 batch(source) < batch(target)，任务恰好出现一次。"""
        rng = random.Random(20261115)
        for _ in range(30):
            size = rng.randint(1, 25)
            tasks = [
                task(
                    f"T{index:02d}",
                    dependencies=tuple(f"T{previous:02d}" for previous in range(index) if rng.random() < 0.25),
                    requirements=("R-01",) if index == 0 else (),
                )
                for index in range(size)
            ]
            derivation = build_plan(tasks, spec("R-01"))

            self.assertTrue(derivation.validation_report.valid, derivation.validation_report.errors)
            layers = {
                task_id: layer
                for layer, batch in enumerate(derivation.parallel_batches)
                for task_id in batch
            }
            self.assertEqual(set(layers), {item.task_id for item in tasks})
            for edge in derivation.edges:
                self.assertLess(layers[edge.source], layers[edge.target])
            self.assertEqual(len(derivation.ordered_task_ids), len(tasks))
            self.assertEqual(set(derivation.ordered_task_ids), set(layers))


class ScanTest(unittest.TestCase):
    def test_only_valid_edges_enter_graph(self) -> None:
        tasks = [
            task("A", requirements=("R-01",)),
            task("B", dependencies=("A", "X", "B")),
        ]
        scan = scan_dependencies(tasks)
        self.assertEqual([(edge.source, edge.target) for edge in scan.edges], [("A", "B")])
        self.assertEqual([item.code for item in scan.issues], ["MISSING_DEPENDENCY", "SELF_DEPENDENCY"])
        self.assertEqual(scan.issues[0].path, task_path(1, "dependencies", 1))
        self.assertEqual(scan.children["A"], ("B",))

    def test_kahn_returns_processed_count_for_cycle_input(self) -> None:
        tasks = [
            task("A", requirements=("R-01",), dependencies=("B",)),
            task("B", dependencies=("A",)),
        ]
        scan = scan_dependencies(tasks)
        batches, processed = kahn_batches(("A", "B"), scan.children)
        self.assertEqual(batches, [])
        self.assertEqual(processed, 0)


if __name__ == "__main__":
    unittest.main()

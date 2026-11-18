"""Measure Q02 orchestration and Q03 persistence performance."""

from __future__ import annotations

import argparse
import json
import math
import random
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys_path = [str(ROOT), str(ROOT / "backend"), str(ROOT / "tech")]

import sys

for path in reversed(sys_path):
    if path not in sys.path:
        sys.path.insert(0, path)

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from flowstudio_contracts import DesignSpecContent, Task  # noqa: E402
from flowstudio_orchestration import build_plan  # noqa: E402


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * ratio) - 1)
    return round(ordered[index], 3)


def spec_payload(task_count: int) -> dict:
    return {
        "schema_version": "1.0",
        "product_name": f"性能基准 {task_count} 任务",
        "background": "用于质量属性测量的确定性抽象规格。",
        "goals": ["验证性能边界"],
        "target_users": ["验收人员"],
        "requirements": [
            {
                "id": "R1",
                "kind": "functional",
                "text": "系统可以完成一项可观察操作",
                "priority": "must",
                "acceptance_criteria": ["结果可观察"],
            }
        ],
        "technical_constraints": [],
        "development_constraints": [],
        "delivery_requirements": ["交付性能报告"],
        "acceptance_criteria": ["目标以内"],
        "supplemental_text": "",
        "confirmed_assumptions": [],
    }


def task_payload(task_id: str, dependencies: list[str], revision: int = 0) -> dict:
    return {
        "task_id": task_id,
        "name": f"性能任务 {task_id} 版本 {revision}",
        "description": f"验证 {task_id} 的规模与持久化边界",
        "category": "build",
        "stage": "build",
        "priority": "medium",
        "assigned_role": "engineer",
        "dependencies": dependencies,
        "inputs": [],
        "deliverables": [{"id": "output", "text": f"{task_id} 的交付"}],
        "acceptance_criteria": ["结果可以观察"],
        "source_requirement_ids": ["R1"],
        "rationale": "",
        "assumptions": [],
        "estimated_effort": None,
    }


def dense_edges(task_count: int, edge_count: int) -> set[tuple[int, int]]:
    edges = {(index, index + 1) for index in range(task_count - 1)}
    candidates = [
        (source, target)
        for source in range(task_count)
        for target in range(source + 1, task_count)
        if (source, target) not in edges
    ]
    edges.update(random.Random(20261118).sample(candidates, edge_count - len(edges)))
    if len(edges) != edge_count:
        raise RuntimeError(f"edge generation mismatch: {len(edges)}")
    return edges


def tasks_from_edges(task_count: int, edges: set[tuple[int, int]]) -> list[Task]:
    dependencies: dict[int, list[str]] = {index: [] for index in range(task_count)}
    for source, target in sorted(edges):
        dependencies[target].append(f"T{source:03d}")
    return [
        Task.model_validate(
            task_payload(
                f"T{index:03d}",
                sorted(dependencies[index]),
            )
        )
        for index in range(task_count)
    ]


def run_q02(iterations: int = 100, warmup: int = 10) -> dict:
    task_count = 100
    edge_count = 1000
    valid_edges = dense_edges(task_count, edge_count)
    removable = next(
        edge
        for edge in sorted(valid_edges, reverse=True)
        if edge != (edge[0], edge[0] + 1)
    )
    invalid_edges = (valid_edges - {removable}) | {(task_count - 1, 0)}
    valid_tasks = tasks_from_edges(task_count, valid_edges)
    invalid_tasks = tasks_from_edges(task_count, invalid_edges)
    spec = DesignSpecContent.model_validate(spec_payload(task_count))

    def invoke(index: int) -> None:
        tasks = valid_tasks if index % 2 == 0 else invalid_tasks
        result = build_plan(tasks, spec, None)
        if index % 2 == 0:
            if not result.validation_report.valid or len(result.parallel_batches) == 0:
                raise RuntimeError("Q02 valid graph unexpectedly failed")
        elif result.validation_report.valid or result.parallel_batches:
            raise RuntimeError("Q02 invalid graph unexpectedly passed")

    for index in range(warmup):
        invoke(index)

    samples: list[float] = []
    for index in range(iterations):
        started = time.perf_counter_ns()
        invoke(index)
        samples.append((time.perf_counter_ns() - started) / 1_000_000)

    p95 = percentile(samples, 0.95)
    return {
        "id": "Q02",
        "task_count": task_count,
        "edge_count": edge_count,
        "warmup": warmup,
        "iterations": iterations,
        "valid_iterations": iterations // 2,
        "invalid_iterations": iterations - iterations // 2,
        "p50_ms": percentile(samples, 0.50),
        "p95_ms": p95,
        "max_ms": round(max(samples), 3),
        "target_p95_ms": 200,
        "status": "PASS" if p95 <= 200 else "FAIL",
    }


def create_project(client: TestClient) -> dict:
    response = client.post("/api/v1/projects", json={"name": "Q03 持久化基准"})
    if response.status_code != 201:
        raise RuntimeError(response.text)
    return response.json()


def create_spec(client: TestClient, project_id: str) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/spec-revisions",
        json={"expected_revision": 0, "content": spec_payload(100)},
    )
    if response.status_code != 201:
        raise RuntimeError(response.text)
    return response.json()


def save_plan(client: TestClient, project_id: str, spec_id: str, tasks: list[dict]) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={
            "spec_revision_id": spec_id,
            "tasks": tasks,
            "confirmed_assumption_ids": [],
        },
    )
    if response.status_code != 201:
        raise RuntimeError(response.text)
    return response.json()


def append_plan(
    client: TestClient,
    plan_id: str,
    spec_id: str,
    parent_id: str,
    expected_revision: int,
    tasks: list[dict],
) -> dict:
    return client.post(
        f"/api/v1/plans/{plan_id}/revisions",
        json={
            "expected_revision": expected_revision,
            "parent_revision_id": parent_id,
            "spec_revision_id": spec_id,
            "tasks": tasks,
            "confirmed_assumption_ids": [],
        },
    )


def run_q03(work_dir: Path) -> dict:
    task_count = 100
    saves = 100
    tasks = [
        task_payload(f"T{index:03d}", [f"T{index - 1:03d}"] if index else [])
        for index in range(task_count)
    ]
    samples: list[float] = []

    with tempfile.TemporaryDirectory(dir=work_dir, prefix="q03-") as temp:
        temp_path = Path(temp)
        data_dir = temp_path / "data"
        settings = Settings(
            data_dir=data_dir,
            database_url=f"sqlite:///{(data_dir / 'flowstudio.db').as_posix()}",
            use_alembic=False,
            instance_lock=False,
            worker_mode="inline",
            fixtures_dir=ROOT / "backend" / "fixtures",
        )
        app = create_app(settings)
        with TestClient(app, raise_server_exceptions=False) as client:
            project = create_project(client)
            spec = create_spec(client, project["id"])

            started = time.perf_counter_ns()
            created = save_plan(client, project["id"], spec["id"], tasks)
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
            plan_id = created["plan_id"]
            revision = created["revision"]

            for number in range(2, saves + 1):
                changed = [dict(item) for item in tasks]
                changed[0] = {
                    **changed[0],
                    "name": f"性能任务 T000 版本 {number}",
                }
                started = time.perf_counter_ns()
                response = append_plan(
                    client,
                    plan_id,
                    spec["id"],
                    revision["id"],
                    number - 1,
                    changed,
                )
                samples.append((time.perf_counter_ns() - started) / 1_000_000)
                if response.status_code != 201:
                    raise RuntimeError(response.text)
                revision = response.json()

            baseline_count = len(
                client.get(f"/api/v1/plans/{plan_id}/revisions", params={"limit": 100}).json()[
                    "items"
                ]
            )
            failed = [dict(item) for item in tasks]
            failed[0] = {**failed[0], "name": "事务失败不应写入"}
            with patch(
                "sqlalchemy.orm.Session.commit",
                side_effect=RuntimeError("injected transaction failure"),
            ):
                response = append_plan(
                    client,
                    plan_id,
                    spec["id"],
                    revision["id"],
                    saves,
                    failed,
                )
            after_failure = client.get(
                f"/api/v1/plans/{plan_id}/revisions", params={"limit": 100}
            ).json()["items"]

    p95 = percentile(samples, 0.95)
    no_partial_write = (
        response.status_code >= 500
        and baseline_count == saves
        and len(after_failure) == saves
        and after_failure[0]["revision"] == saves
    )
    return {
        "id": "Q03",
        "task_count": task_count,
        "saves": saves,
        "p50_ms": percentile(samples, 0.50),
        "p95_ms": p95,
        "max_ms": round(max(samples), 3),
        "target_p95_ms": 500,
        "injected_failure_status": response.status_code,
        "revisions_before_failure": baseline_count,
        "revisions_after_failure": len(after_failure),
        "no_partial_write": no_partial_write,
        "status": "PASS" if p95 <= 500 and no_partial_write else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python": sys.version.split()[0],
        "q02": run_q02(iterations=args.iterations),
        "q03": run_q03(args.output.parent),
    }
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["q02"]["status"] == result["q03"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""campus 演示 fixture 与仓库已提交规格的绑定校验。

防止 spec 改动后 fixture 静默失效：需求 ID 必须存在、must 需求必须全覆盖、
依赖必须指向真实任务且无环。
"""

from __future__ import annotations

import json
from pathlib import Path

from flowstudio_contracts import TaskProposal

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = ROOT / "backend" / "fixtures" / "campus.json"
SPEC_PATH = ROOT / "delivery" / "inputs" / "campus-meeting-spec.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_fixture_satisfies_contract() -> None:
    proposal = TaskProposal.model_validate(load_fixture())
    assert proposal.tasks, "campus fixture 至少需要一个任务"


def test_fixture_requirement_ids_exist_in_spec() -> None:
    spec_ids = {item["id"] for item in load_spec()["requirements"]}
    for task in load_fixture()["tasks"]:
        unknown = set(task["source_requirement_ids"]) - spec_ids
        assert not unknown, f"任务 {task['task_id']} 引用了规格中不存在的需求 {sorted(unknown)}"


def test_fixture_covers_all_must_requirements() -> None:
    must_ids = {
        item["id"] for item in load_spec()["requirements"] if item["priority"] == "must"
    }
    covered = {
        requirement_id
        for task in load_fixture()["tasks"]
        for requirement_id in task["source_requirement_ids"]
    }
    assert must_ids <= covered, f"未覆盖的必需需求：{sorted(must_ids - covered)}"


def test_fixture_dependencies_are_valid_and_acyclic() -> None:
    tasks = load_fixture()["tasks"]
    task_ids = {task["task_id"] for task in tasks}
    assert len(task_ids) == len(tasks), "任务 ID 重复"

    indegree = {task_id: 0 for task_id in task_ids}
    outgoing: dict[str, list[str]] = {task_id: [] for task_id in task_ids}
    for task in tasks:
        for dependency in task["dependencies"]:
            assert dependency in task_ids, f"任务 {task['task_id']} 依赖不存在的 {dependency}"
            assert dependency != task["task_id"], f"任务 {task['task_id']} 依赖自己"
            outgoing[dependency].append(task["task_id"])
            indegree[task["task_id"]] += 1

    ready = [task_id for task_id, degree in indegree.items() if degree == 0]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for follower in outgoing[current]:
            indegree[follower] -= 1
            if indegree[follower] == 0:
                ready.append(follower)

    assert visited == len(task_ids), "campus fixture 的依赖存在环"

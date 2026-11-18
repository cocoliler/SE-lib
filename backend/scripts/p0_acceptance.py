"""Cross-module P0 acceptance checks over a real HTTP backend.

This script covers the non-REAL technical closure path and writes a small state file
so a second invocation can verify persistence after an actual process restart.

    python scripts/p0_acceptance.py --base-url http://127.0.0.1:8765 \
        --state-file evidence/runs/<timestamp>/p0-state.json

    # After stopping and starting the backend with the same data directory:
    python scripts/p0_acceptance.py --phase verify --base-url http://127.0.0.1:8765 \
        --state-file evidence/runs/<timestamp>/p0-state.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


class AcceptanceError(RuntimeError):
    pass


def call(
    base_url: str,
    method: str,
    path: str,
    body: dict | None = None,
    *,
    expected: int | tuple[int, ...],
) -> tuple[int, dict]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        base_url + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status = response.status
            payload = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read()
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {"raw": raw.decode("utf-8", "replace")}

    accepted = expected if isinstance(expected, tuple) else (expected,)
    if status not in accepted:
        raise AcceptanceError(
            f"{method} {path} returned {status}, expected {accepted}: "
            + json.dumps(payload, ensure_ascii=False)
        )
    return status, payload


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def require_error_code(payload: dict, code: str) -> None:
    error = payload.get("error", {})
    actual = {error.get("code")}
    actual.update(issue.get("code") for issue in error.get("issues", []))
    require(code in actual, f"expected error code {code}, got {actual}: {payload}")


def requirement(requirement_id: str = "R1", *, required: bool = True) -> dict:
    return {
        "id": requirement_id,
        "kind": "functional",
        "text": f"用户可以完成 {requirement_id}",
        "priority": "must" if required else "should",
        "acceptance_criteria": ["结果可以观察"],
    }


def spec_content(product_name: str, requirements: list[dict] | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "product_name": product_name,
        "background": "用于跨模块 P0 验收的中性背景。",
        "goals": ["验证项目、规格、计划和导出链路"],
        "target_users": ["验收人员"],
        "requirements": requirements
        or [requirement("R1"), requirement("R2", required=False)],
        "technical_constraints": [],
        "development_constraints": [],
        "delivery_requirements": ["交付可运行原型"],
        "acceptance_criteria": ["关键路径可以观察"],
        "supplemental_text": "",
        "confirmed_assumptions": [],
    }


def task(
    task_id: str,
    *,
    dependencies: tuple[str, ...] = (),
    inputs: tuple[dict, ...] = (),
    name: str | None = None,
) -> dict:
    return {
        "task_id": task_id,
        "name": name or f"任务 {task_id}",
        "description": f"完成 {task_id} 的可验收交付",
        "category": "build",
        "stage": "build",
        "priority": "medium",
        "assigned_role": "engineer",
        "dependencies": list(dependencies),
        "inputs": list(inputs),
        "deliverables": [{"id": "result", "text": f"{task_id} 的交付"}],
        "acceptance_criteria": ["结果可以观察"],
        "source_requirement_ids": ["R1"],
        "rationale": "",
        "assumptions": [],
        "estimated_effort": None,
    }


def input_task(task_id: str, deliverable_id: str = "result") -> dict:
    return {"kind": "task", "task_id": task_id, "deliverable_id": deliverable_id}


def diamond_tasks() -> list[dict]:
    return [
        task("A"),
        task("B", dependencies=("A",), inputs=(input_task("A"),)),
        task("C", dependencies=("A",), inputs=(input_task("A"),)),
        task(
            "D",
            dependencies=("B", "C"),
            inputs=(input_task("B"), input_task("C")),
        ),
    ]


def create_project(base_url: str, name: str) -> dict:
    _, body = call(base_url, "POST", "/api/v1/projects", {"name": name}, expected=201)
    return body


def create_spec(base_url: str, project_id: str, expected_revision: int, content: dict) -> dict:
    _, body = call(
        base_url,
        "POST",
        f"/api/v1/projects/{project_id}/spec-revisions",
        {"expected_revision": expected_revision, "content": content},
        expected=201,
    )
    return body


def orchestrate(base_url: str, spec_revision_id: str, tasks: list[dict]) -> dict:
    _, body = call(
        base_url,
        "POST",
        "/api/v1/orchestrations",
        {"spec_revision_id": spec_revision_id, "tasks": tasks},
        expected=200,
    )
    return body


def check_invalid_graph(
    base_url: str,
    spec_revision_id: str,
    label: str,
    tasks: list[dict],
    expected_code: str,
) -> None:
    derivation = orchestrate(base_url, spec_revision_id, tasks)
    report = derivation["validation_report"]
    codes = {issue["code"] for issue in report["errors"]}
    require(not report["valid"], f"A06 {label}: invalid graph was accepted")
    require(expected_code in codes, f"A06 {label}: expected {expected_code}, got {codes}")
    require(derivation["parallel_batches"] == [], f"A06 {label}: invalid graph returned batches")


def run_full(base_url: str, state_file: Path) -> None:
    project_one = create_project(base_url, "P0 验收项目甲")
    project_two = create_project(base_url, "P0 验收项目乙")
    first_spec = create_spec(base_url, project_one["id"], 0, spec_content("P0 产品甲"))
    other_spec = create_spec(base_url, project_two["id"], 0, spec_content("P0 产品乙"))

    _, project_one_specs = call(
        base_url, "GET", f"/api/v1/projects/{project_one['id']}/spec-revisions", expected=200
    )
    _, project_two_specs = call(
        base_url, "GET", f"/api/v1/projects/{project_two['id']}/spec-revisions", expected=200
    )
    require([item["id"] for item in project_one_specs["items"]] == [first_spec["id"]], "A01 project one spec leak")
    require([item["id"] for item in project_two_specs["items"]] == [other_spec["id"]], "A01 project two spec leak")

    _, cross_project = call(
        base_url,
        "POST",
        f"/api/v1/projects/{project_one['id']}/plans",
        {
            "spec_revision_id": other_spec["id"],
            "tasks": [task("A")],
            "confirmed_assumption_ids": [],
        },
        expected=422,
    )
    require_error_code(cross_project, "SOURCE_MISMATCH")
    print("[PASS] A01 project isolation and cross-project rejection")

    second_spec = create_spec(
        base_url,
        project_one["id"],
        1,
        spec_content("P0 产品甲 v2"),
    )
    _, old_spec = call(base_url, "GET", f"/api/v1/spec-revisions/{first_spec['id']}", expected=200)
    _, new_spec = call(base_url, "GET", f"/api/v1/spec-revisions/{second_spec['id']}", expected=200)
    require(old_spec["hash"] == first_spec["hash"], "A02 first spec hash changed")
    require(old_spec["content"]["product_name"] == "P0 产品甲", "A02 first spec content changed")
    require(new_spec["revision"] == 2, "A02 second spec revision mismatch")
    require(new_spec["content"]["product_name"] == "P0 产品甲 v2", "A02 second spec content mismatch")
    print("[PASS] A02 immutable independent spec revisions")

    duplicate_spec = spec_content(
        "重复需求项目",
        [requirement("R1"), requirement("R1")],
    )
    _, duplicate = call(
        base_url,
        "POST",
        f"/api/v1/projects/{project_two['id']}/spec-revisions",
        {"expected_revision": 1, "content": duplicate_spec},
        expected=422,
    )
    require_error_code(duplicate, "VALIDATION_FAILED")
    _, history_after_duplicate = call(
        base_url, "GET", f"/api/v1/projects/{project_two['id']}/spec-revisions", expected=200
    )
    require(len(history_after_duplicate["items"]) == 1, "A03 invalid spec changed revision history")
    print("[PASS] A03 invalid spec blocked with no new version")

    duplicate_tasks = [task("A"), task("A")]
    missing_dependency = [task("A"), task("B", dependencies=("X",))]
    self_dependency = [task("A", dependencies=("A",))]
    cycle = [task("A", dependencies=("B",)), task("B", dependencies=("A",))]
    missing_input = [
        task("A"),
        task("B", dependencies=("A",), inputs=(input_task("A", "missing"),)),
    ]
    check_invalid_graph(base_url, second_spec["id"], "duplicate", duplicate_tasks, "DUPLICATE_ID")
    check_invalid_graph(
        base_url, second_spec["id"], "missing", missing_dependency, "MISSING_DEPENDENCY"
    )
    check_invalid_graph(base_url, second_spec["id"], "self", self_dependency, "SELF_DEPENDENCY")
    check_invalid_graph(base_url, second_spec["id"], "cycle", cycle, "CYCLE")
    check_invalid_graph(base_url, second_spec["id"], "input", missing_input, "MISSING_INPUT")
    print("[PASS] A06 invalid graphs rejected with actionable codes")

    tasks = diamond_tasks()
    derivation = orchestrate(base_url, second_spec["id"], tasks)
    require(derivation["parallel_batches"] == [["A"], ["B", "C"], ["D"]], "A07 diamond batches mismatch")
    require(derivation["validation_report"]["valid"], "A07 valid diamond was rejected")

    _, created = call(
        base_url,
        "POST",
        f"/api/v1/projects/{project_one['id']}/plans",
        {
            "spec_revision_id": second_spec["id"],
            "tasks": tasks,
            "confirmed_assumption_ids": [],
        },
        expected=201,
    )
    first_revision = created["revision"]
    plan_id = created["plan_id"]

    _, layout = call(
        base_url,
        "PUT",
        f"/api/v1/plan-revisions/{first_revision['id']}/layout",
        {
            "expected_revision": 0,
            "positions": {
                "A": {"x": 10, "y": 20},
                "B": {"x": 300, "y": 40},
                "C": {"x": 300, "y": 200},
                "D": {"x": 600, "y": 100},
            },
            "notes": [{"id": "note-1", "text": "P0 验收", "x": 0, "y": 0}],
            "viewport": {"x": 0, "y": 0, "zoom": 1.0},
        },
        expected=200,
    )
    require(layout["revision"] == 1, "A07 layout revision mismatch")
    after_layout = orchestrate(base_url, second_spec["id"], tasks)
    require(after_layout["input_hash"] == derivation["input_hash"], "A07 layout changed input hash")
    require(
        after_layout["parallel_batches"] == derivation["parallel_batches"],
        "A07 layout changed parallel batches",
    )
    require(
        after_layout["ordered_task_ids"] == derivation["ordered_task_ids"],
        "A07 layout changed task order",
    )
    print("[PASS] A07 deterministic batches and layout independence")

    edited = [dict(item) for item in tasks]
    edited[0] = {**edited[0], "name": "已修改任务 A"}
    _, appended = call(
        base_url,
        "POST",
        f"/api/v1/plans/{plan_id}/revisions",
        {
            "expected_revision": 1,
            "parent_revision_id": first_revision["id"],
            "spec_revision_id": second_spec["id"],
            "tasks": edited,
            "confirmed_assumption_ids": [],
        },
        expected=201,
    )
    second_revision = appended
    require(second_revision["revision"] == 2, "A09 second revision mismatch")
    _, stale = call(
        base_url,
        "POST",
        f"/api/v1/plans/{plan_id}/revisions",
        {
            "expected_revision": 1,
            "spec_revision_id": second_spec["id"],
            "tasks": tasks,
            "confirmed_assumption_ids": [],
        },
        expected=409,
    )
    require_error_code(stale, "REVISION_CONFLICT")
    _, old_plan = call(
        base_url, "GET", f"/api/v1/plan-revisions/{first_revision['id']}", expected=200
    )
    require(old_plan["hash"] == first_revision["hash"], "A09 first revision hash changed")
    require(old_plan["tasks"][0]["name"] != "已修改任务 A", "A09 first revision content changed")
    print("[PASS] A09 new revision and stale-write conflict")

    _, bundle = call(
        base_url,
        "GET",
        f"/api/v1/plan-revisions/{first_revision['id']}/export?format=json",
        expected=200,
    )
    require(bundle["layout"]["revision"] == 1, "A10 export lost layout revision")
    require(bundle["plan_revision"]["hash"] == first_revision["hash"], "A10 export plan hash changed")

    state = {
        "project_id": project_one["id"],
        "spec_revision_ids": [first_spec["id"], second_spec["id"]],
        "spec_hashes": [first_spec["hash"], second_spec["hash"]],
        "plan_id": plan_id,
        "plan_revision_ids": [first_revision["id"], second_revision["id"]],
        "plan_hashes": [first_revision["hash"], second_revision["hash"]],
        "layout_revision": 1,
    }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print("[PASS] A10 export and restart state recorded")


def run_verify(base_url: str, state_file: Path) -> None:
    require(state_file.is_file(), f"restart state missing: {state_file}")
    state = json.loads(state_file.read_text(encoding="utf-8"))

    for revision_id, expected_hash in zip(
        state["spec_revision_ids"], state["spec_hashes"], strict=True
    ):
        _, revision = call(
            base_url, "GET", f"/api/v1/spec-revisions/{revision_id}", expected=200
        )
        require(revision["hash"] == expected_hash, f"A10 spec hash changed after restart: {revision_id}")

    _, revisions = call(
        base_url,
        "GET",
        f"/api/v1/plans/{state['plan_id']}/revisions",
        expected=200,
    )
    require(
        [item["revision"] for item in revisions["items"]] == [2, 1],
        "A10 plan history changed after restart",
    )

    for revision_id, expected_hash in zip(
        state["plan_revision_ids"], state["plan_hashes"], strict=True
    ):
        _, revision = call(
            base_url, "GET", f"/api/v1/plan-revisions/{revision_id}", expected=200
        )
        require(revision["hash"] == expected_hash, f"A10 plan hash changed after restart: {revision_id}")

    _, bundle = call(
        base_url,
        "GET",
        f"/api/v1/plan-revisions/{state['plan_revision_ids'][0]}/export?format=json",
        expected=200,
    )
    require(bundle["layout"]["revision"] == state["layout_revision"], "A10 layout lost after restart")
    require(
        bundle["plan_revision"]["hash"] == state["plan_hashes"][0],
        "A10 export hash changed after restart",
    )
    print("[PASS] A10 history and export survive actual backend restart")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--phase", choices=("full", "verify"), default="full")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    try:
        if args.phase == "full":
            run_full(base, args.state_file)
        else:
            run_verify(base, args.state_file)
    except AcceptanceError as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    print(f"PASS P0 HTTP acceptance phase={args.phase}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

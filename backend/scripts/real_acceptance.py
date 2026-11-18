"""Run A04/A05/A11 against a real PlanningRun and record local evidence."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tech"))

from flowstudio_contracts import PROMPT_VERSION, RULES_VERSION  # noqa: E402


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
        with urllib.request.urlopen(request, timeout=30) as response:
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


def create_project(base_url: str, name: str) -> dict:
    _, payload = call(base_url, "POST", "/api/v1/projects", {"name": name}, expected=201)
    return payload


def create_spec(base_url: str, project_id: str, revision: int, content: dict) -> dict:
    _, payload = call(
        base_url,
        "POST",
        f"/api/v1/projects/{project_id}/spec-revisions",
        {"expected_revision": revision, "content": content},
        expected=201,
    )
    return payload


def run_real(base_url: str, spec_revision_id: str, granularity: str = "standard") -> tuple[dict, float]:
    config = {
        "model": "configured-default",
        "granularity": granularity,
        "planning_constraints": [],
    }
    started = time.monotonic()
    _, created = call(
        base_url,
        "POST",
        "/api/v1/planning-runs",
        {"spec_revision_id": spec_revision_id, "mode": "REAL", "config": config},
        expected=202,
    )
    run = created
    deadline = time.monotonic() + 220
    while time.monotonic() < deadline:
        _, run = call(base_url, "GET", f"/api/v1/planning-runs/{created['id']}", expected=200)
        if run["status"] in {"SUCCEEDED", "NEEDS_INPUT", "FAILED"}:
            break
        time.sleep(2)
    elapsed = round(time.monotonic() - started, 3)
    if run["status"] not in {"SUCCEEDED", "NEEDS_INPUT", "FAILED"}:
        raise AcceptanceError(f"PlanningRun did not reach a terminal state: {run}")
    return run, elapsed


def task_fingerprint(task: dict) -> str:
    fields = (
        "name",
        "description",
        "category",
        "stage",
        "priority",
        "assigned_role",
        "dependencies",
        "inputs",
        "deliverables",
        "acceptance_criteria",
        "source_requirement_ids",
        "rationale",
        "assumptions",
        "estimated_effort",
    )
    return json.dumps({field: task.get(field) for field in fields}, ensure_ascii=False, sort_keys=True)


def review_candidate(spec: dict, run: dict) -> dict:
    require(run["status"] == "SUCCEEDED", f"A04 REAL run ended with {run['status']}: {run.get('error')}")
    require(run["mode"] == "REAL", "A04 expected REAL mode")
    require(run["attempt_count"] >= 1, "A04 no Provider attempt was recorded")
    require(run.get("usage") is not None, "A04 usage was not recorded")
    require(run.get("validation_report", {}).get("valid") is True, "A04 candidate failed validation")

    tasks = run["proposal"]["tasks"]
    require(bool(tasks), "A04 REAL run returned no tasks")
    task_ids = [task["task_id"] for task in tasks]
    require(len(task_ids) == len(set(task_ids)), "A05 duplicate task IDs")
    known_ids = set(task_ids)
    for item in tasks:
        require(bool(item["deliverables"]), f"A05 {item['task_id']} has no deliverable")
        require(bool(item["acceptance_criteria"]), f"A05 {item['task_id']} has no acceptance criterion")
        require(
            set(item["dependencies"]) <= known_ids,
            f"A05 {item['task_id']} has an unknown dependency",
        )
        require(
            set(item["source_requirement_ids"]) <= {req["id"] for req in spec["requirements"]},
            f"A05 {item['task_id']} has an unknown requirement reference",
        )

    mapping = []
    for req in spec["requirements"]:
        matching = [
            {
                "task_id": item["task_id"],
                "name": item["name"],
                "deliverables": item["deliverables"],
                "acceptance_criteria": item["acceptance_criteria"],
            }
            for item in tasks
            if req["id"] in item["source_requirement_ids"]
        ]
        if req["priority"] == "must":
            require(bool(matching), f"A05 must requirement {req['id']} has no task")
        mapping.append(
            {
                "requirement_id": req["id"],
                "priority": req["priority"],
                "text": req["text"],
                "tasks": matching,
                "human_verdict": "pending",
                "reviewer": None,
                "notes": "",
            }
        )

    return {
        "structure_status": "PASS",
        "task_count": len(tasks),
        "task_ids": task_ids,
        "attempt_count": run["attempt_count"],
        "usage": run.get("usage"),
        "validation_report": run.get("validation_report"),
        "proposal": run.get("proposal"),
        "requirement_mapping": mapping,
        "human_review_status": "pending",
    }


def relevant_change(before: dict, after: dict, requirement_id: str) -> dict:
    before_tasks = {
        item["task_id"]: task_fingerprint(item)
        for item in before["proposal"]["tasks"]
        if requirement_id in item["source_requirement_ids"]
    }
    after_tasks = {
        item["task_id"]: task_fingerprint(item)
        for item in after["proposal"]["tasks"]
        if requirement_id in item["source_requirement_ids"]
    }
    changed_ids = sorted(
        task_id
        for task_id in set(before_tasks) | set(after_tasks)
        if before_tasks.get(task_id) != after_tasks.get(task_id)
    )
    return {
        "requirement_id": requirement_id,
        "before_task_ids": sorted(before_tasks),
        "after_task_ids": sorted(after_tasks),
        "changed_task_ids": changed_ids,
        "meaningful_change": bool(changed_ids),
    }


def plan_difference(before: dict, after: dict) -> dict:
    before_tasks = {
        item["task_id"]: task_fingerprint(item) for item in before["proposal"]["tasks"]
    }
    after_tasks = {
        item["task_id"]: task_fingerprint(item) for item in after["proposal"]["tasks"]
    }
    changed_ids = sorted(
        task_id
        for task_id in set(before_tasks) | set(after_tasks)
        if before_tasks.get(task_id) != after_tasks.get(task_id)
    )
    return {
        "before_task_count": len(before_tasks),
        "after_task_count": len(after_tasks),
        "changed_task_ids": changed_ids,
        "same_task_signatures": sorted(before_tasks.values()) == sorted(after_tasks.values()),
        "meaningful_change": (
            len(before_tasks) != len(after_tasks)
            or sorted(before_tasks.values()) != sorted(after_tasks.values())
        ),
    }


def mutate_one_must_requirement(spec: dict) -> tuple[dict, str]:
    changed = copy.deepcopy(spec)
    target = next((item for item in changed["requirements"] if item["priority"] == "must"), None)
    require(target is not None, "A11 spec has no must requirement to mutate")
    marker = "验收变化：界面必须展示最近一次数据同步状态，并为失败提供可操作的恢复入口。"
    target["text"] = target["text"].rstrip() + marker
    target["acceptance_criteria"].append(
        "可以观察到同步状态，并能根据失败原因执行明确的重试或修正操作"
    )
    return changed, target["id"]


def write_evidence(path: Path, evidence: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    evidence = {
        "status": "RUNNING",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "input_spec": str(args.spec),
        "model_config": "configured-default",
        "prompt_version": PROMPT_VERSION,
        "rules_version": RULES_VERSION,
        "real_executed": False,
    }
    try:
        content = json.loads(args.spec.read_text(encoding="utf-8"))
        call(base, "GET", "/api/v1/projects", expected=200)
        project = create_project(base, "REAL 验收：跨园区会议室")
        first_spec = create_spec(base, project["id"], 0, content)
        evidence["real_executed"] = True
        evidence["project_id"] = project["id"]
        evidence["baseline_spec"] = first_spec

        print("[1/7] REAL baseline planning")
        baseline, baseline_seconds = run_real(base, first_spec["id"])
        evidence["baseline"] = {
            "elapsed_seconds": baseline_seconds,
            "run": baseline,
        }
        baseline_review = review_candidate(content, baseline)
        evidence["baseline"]["review"] = baseline_review
        print(
            f"      status={baseline['status']} tasks={baseline_review['task_count']} "
            f"attempts={baseline['attempt_count']} elapsed={baseline_seconds}s"
        )

        print("[2/7] A05 structural review")
        must_coverage = [
            item["requirement_id"]
            for item in baseline_review["requirement_mapping"]
            if item["priority"] == "must" and item["tasks"]
        ]
        must_ids = {
            req["id"] for req in content["requirements"] if req["priority"] == "must"
        }
        require(set(must_coverage) == must_ids, "A05 must requirement mapping is incomplete")
        evidence["a05_structural_review"] = "PASS"
        evidence["a05_human_review"] = "PENDING"
        print("      structural coverage PASS; human semantic sign-off PENDING")

        print("[3/7] Observe a semantic requirement change")
        variant_content, changed_requirement = mutate_one_must_requirement(content)
        variant_spec = create_spec(base, project["id"], 1, variant_content)
        evidence["variant_spec"] = variant_spec
        evidence["changed_requirement_id"] = changed_requirement

        print("[4/7] REAL requirement-change planning")
        variant, variant_seconds = run_real(base, variant_spec["id"])
        evidence["requirement_variation"] = {
            "elapsed_seconds": variant_seconds,
            "run": variant,
        }
        if variant["status"] == "SUCCEEDED":
            variant_review = review_candidate(variant_content, variant)
            comparison = relevant_change(baseline, variant, changed_requirement)
            evidence["requirement_variation"]["review"] = variant_review
            evidence["requirement_variation"]["comparison"] = comparison
            print(
                f"      status=SUCCEEDED tasks={variant_review['task_count']} "
                f"attempts={variant['attempt_count']} elapsed={variant_seconds}s"
            )
        else:
            questions = (variant.get("proposal") or {}).get("blocking_questions", [])
            evidence["requirement_variation"]["blocking_questions"] = questions
            print(
                f"      status={variant['status']} attempts={variant['attempt_count']} "
                f"blocking_questions={len(questions)}"
            )

        print("[5/7] A11 REAL granularity variation")
        coarse, coarse_seconds = run_real(base, first_spec["id"], granularity="coarse")
        evidence["granularity_variation"] = {
            "from": "standard",
            "to": "coarse",
            "elapsed_seconds": coarse_seconds,
            "run": coarse,
        }
        coarse_review = review_candidate(content, coarse)
        evidence["granularity_variation"]["review"] = coarse_review
        print(
            f"      status={coarse['status']} tasks={coarse_review['task_count']} "
            f"attempts={coarse['attempt_count']} elapsed={coarse_seconds}s"
        )

        print("[6/7] Compare standard and coarse plans")
        comparison = plan_difference(baseline, coarse)
        evidence["granularity_comparison"] = comparison
        require(comparison["meaningful_change"], "A11 standard and coarse plans did not change")
        print(
            f"      tasks {comparison['before_task_count']} -> {comparison['after_task_count']}; "
            f"changed task ids: {', '.join(comparison['changed_task_ids'])}"
        )

        evidence["a04"] = "PASS"
        evidence["a11"] = "PASS"
        evidence["requirement_change_guard"] = (
            "NEEDS_INPUT"
            if evidence["requirement_variation"]["run"]["status"] == "NEEDS_INPUT"
            else evidence["requirement_variation"]["run"]["status"]
        )
        evidence["status"] = "PASS_WITH_HUMAN_REVIEW_PENDING"
    except Exception as error:
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
        evidence["status"] = "FAILED"
        evidence["error"] = {"type": type(error).__name__, "message": str(error)}
        write_evidence(args.evidence, evidence)
        print(f"FAIL {error}", file=sys.stderr)
        return 1

    evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_evidence(args.evidence, evidence)
    print("[7/7] Evidence recorded")
    print(f"PASS A04/A11 technical acceptance; A05 human review pending")
    print(f"Evidence: {args.evidence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

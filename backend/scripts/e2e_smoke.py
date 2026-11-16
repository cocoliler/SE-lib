"""真实 HTTP 端到端自证：项目 → 规格 → 规划 → 计划 → 布局 → 导出。

默认对本地服务执行（先运行 .\\scripts\\dev.ps1）：
    python scripts/e2e_smoke.py --base-url http://127.0.0.1:8000

只使用标准库；任一步不符合预期即以非零码退出，便于 F 直接作为验收证据。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

SPEC_CONTENT = {
    "schema_version": "1.0",
    "product_name": "E2E 自证项目",
    "background": "用于验证后端闭环的中性背景。",
    "goals": ["验证规划到导出的完整链路"],
    "target_users": ["验收人员"],
    "requirements": [
        {
            "id": "R1",
            "kind": "functional",
            "text": "用户可以完成主要操作",
            "priority": "must",
            "acceptance_criteria": ["可以观察的结果"],
        },
        {
            "id": "R2",
            "kind": "functional",
            "text": "用户可以完成次要操作",
            "priority": "should",
            "acceptance_criteria": ["可以观察的结果"],
        },
        {
            "id": "N1",
            "kind": "nonfunctional",
            "text": "性能满足基本要求",
            "priority": "could",
            "acceptance_criteria": ["可以观察的结果"],
        },
    ],
    "technical_constraints": [],
    "development_constraints": [],
    "delivery_requirements": ["交付可运行原型"],
    "acceptance_criteria": ["关键路径可用"],
    "supplemental_text": "",
    "confirmed_assumptions": [],
}


def call(
    base_url: str,
    method: str,
    path: str,
    body: dict | None = None,
    *,
    expected: int | tuple[int, ...] | None = None,
) -> dict:
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

    if expected is not None and status not in (expected if isinstance(expected, tuple) else (expected,)):
        raise SystemExit(f"FAIL {method} {path} -> {status}: {json.dumps(payload, ensure_ascii=False)}")
    return {"status": status, "body": payload}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print(f"[1/8] 服务可达：GET /api/v1/projects @ {base}")
    call(base, "GET", "/api/v1/projects", expected=200)

    print("[2/8] 创建项目")
    project = call(base, "POST", "/api/v1/projects", {"name": "E2E 自证项目"}, expected=201)["body"]
    project_id = project["id"]

    print("[3/8] 保存规格")
    spec = call(
        base,
        "POST",
        f"/api/v1/projects/{project_id}/spec-revisions",
        {"expected_revision": 0, "content": SPEC_CONTENT},
        expected=201,
    )["body"]
    spec_revision_id = spec["id"]

    print("[4/8] 触发 TEST 模式规划（fixture=diamond）")
    run = call(
        base,
        "POST",
        "/api/v1/planning-runs",
        {
            "spec_revision_id": spec_revision_id,
            "mode": "TEST",
            "config": {
                "model": "configured-default",
                "granularity": "standard",
                "planning_constraints": [],
            },
            "fixture_id": "diamond",
        },
        expected=202,
    )["body"]

    print("[5/8] 轮询规划结果")
    for _ in range(60):
        run = call(base, "GET", f"/api/v1/planning-runs/{run['id']}", expected=200)["body"]
        if run["status"] in ("SUCCEEDED", "NEEDS_INPUT", "FAILED"):
            break
        time.sleep(0.5)
    if run["status"] != "SUCCEEDED":
        print(f"FAIL 规划状态 {run['status']}: {json.dumps(run, ensure_ascii=False)}")
        return 1
    tasks = run["proposal"]["tasks"]
    print(f"      规划成功，任务数 {len(tasks)}")

    print("[6/8] 保存计划版本")
    created = call(
        base,
        "POST",
        f"/api/v1/projects/{project_id}/plans",
        {
            "spec_revision_id": spec_revision_id,
            "planning_run_id": run["id"],
            "tasks": tasks,
            "confirmed_assumption_ids": [],
        },
        expected=201,
    )["body"]
    revision = created["revision"]
    if not revision["validation_report"]["valid"]:
        print(f"FAIL 计划校验未通过: {json.dumps(revision['validation_report'], ensure_ascii=False)}")
        return 1

    print("[7/8] 写入布局（独立 CAS）")
    layout = call(
        base,
        "PUT",
        f"/api/v1/plan-revisions/{revision['id']}/layout",
        {
            "expected_revision": 0,
            "positions": {tasks[0]["task_id"]: {"x": 40, "y": 60}},
            "notes": [{"id": "note-1", "text": "E2E 标注", "x": 0, "y": 0}],
            "viewport": {"x": 0, "y": 0, "zoom": 1.0},
        },
        expected=200,
    )["body"]
    if layout["revision"] != 1:
        print(f"FAIL 布局版本应为 1，实际 {layout['revision']}")
        return 1

    print("[8/8] 导出快照并校验未知路径信封")
    bundle = call(
        base,
        "GET",
        f"/api/v1/plan-revisions/{revision['id']}/export?format=json",
        expected=200,
    )["body"]
    if bundle["layout"]["revision"] != 1:
        print("FAIL 导出未包含最新布局")
        return 1
    missing = call(base, "GET", "/api/v1/nope", expected=404)["body"]
    if missing.get("error", {}).get("code") != "NOT_FOUND":
        print(f"FAIL 未知路径未返回契约信封: {json.dumps(missing, ensure_ascii=False)}")
        return 1

    print("PASS 项目 → 规格 → 规划 → 计划 → 布局 → 导出 全链路通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

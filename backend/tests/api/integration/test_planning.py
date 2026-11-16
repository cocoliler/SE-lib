"""PlanningRun：模式校验、202 轮询、终态、结果读取。"""

from __future__ import annotations

import uuid

from api_support import create_project, create_spec, make_planning_run

CONFIG = {"model": "configured-default", "granularity": "standard", "planning_constraints": []}


def _setup(client):
    project = create_project(client)
    spec = create_spec(client, project["id"])
    return project, spec


def test_test_mode_requires_fixture(client) -> None:
    _, spec = _setup(client)
    response = client.post(
        "/api/v1/planning-runs",
        json={"spec_revision_id": spec["id"], "mode": "TEST", "config": CONFIG},
    )
    assert response.status_code == 422
    assert "fixture_id" in response.json()["error"]["message"]


def test_unknown_fixture_rejected(client) -> None:
    _, spec = _setup(client)
    response = client.post(
        "/api/v1/planning-runs",
        json={
            "spec_revision_id": spec["id"],
            "mode": "TEST",
            "config": CONFIG,
            "fixture_id": "nope",
        },
    )
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "VALIDATION_FAILED"
    assert "不存在" in body["message"]


def test_real_mode_forbids_fixture(client) -> None:
    _, spec = _setup(client)
    response = client.post(
        "/api/v1/planning-runs",
        json={
            "spec_revision_id": spec["id"],
            "mode": "REAL",
            "config": CONFIG,
            "fixture_id": "diamond",
        },
    )
    assert response.status_code == 422
    assert "fixture_id" in response.json()["error"]["message"]


def test_unknown_model_rejected(client) -> None:
    _, spec = _setup(client)
    response = client.post(
        "/api/v1/planning-runs",
        json={
            "spec_revision_id": spec["id"],
            "mode": "REAL",
            "config": {**CONFIG, "model": "not-allowlisted"},
        },
    )
    assert response.status_code == 422
    assert "allowlist" in response.json()["error"]["message"]


def test_unknown_spec_revision_returns_404(client) -> None:
    response = client.post(
        "/api/v1/planning-runs",
        json={
            "spec_revision_id": "00000000-0000-4000-8000-000000000000",
            "mode": "TEST",
            "config": CONFIG,
            "fixture_id": "diamond",
        },
    )
    assert response.status_code == 404


def test_test_run_succeeds_and_exposes_tasks(client) -> None:
    _, spec = _setup(client)
    created = make_planning_run(client, spec["id"])
    assert created["status"] == "QUEUED"
    assert created["poll_url"].endswith(created["id"])

    run = client.get(f"/api/v1/planning-runs/{created['id']}").json()
    assert run["status"] == "SUCCEEDED"
    assert run["mode"] == "TEST"
    assert run["attempt_count"] == 1
    assert run["proposal"]["schema_version"] == "1.0"
    assert run["validation_report"]["valid"] is True
    assert run["config_snapshot"]["model"] == "deepseek-chat"  # configured-default 已解析

    tasks = client.get(f"/api/v1/planning-runs/{created['id']}/tasks").json()["tasks"]
    assert {item["task_id"] for item in tasks} == {"A", "B", "C", "D"}


def test_real_run_fails_without_adapter(client) -> None:
    _, spec = _setup(client)
    response = client.post(
        "/api/v1/planning-runs",
        json={"spec_revision_id": spec["id"], "mode": "REAL", "config": CONFIG},
    )
    assert response.status_code == 202
    run = client.get(f"/api/v1/planning-runs/{response.json()['id']}").json()
    assert run["status"] == "FAILED"
    assert run["error"]["code"] == "MODEL_AUTH"


def test_needs_input_run_blocks_task_read(client) -> None:
    _, spec = _setup(client)
    created = make_planning_run(client, spec["id"], fixture="blocked")
    run = client.get(f"/api/v1/planning-runs/{created['id']}").json()
    assert run["status"] == "NEEDS_INPUT"
    assert run["proposal"]["blocking_questions"]

    response = client.get(f"/api/v1/planning-runs/{created['id']}/tasks")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESULT_NOT_READY"


def test_create_planning_run_is_idempotent(client) -> None:
    _, spec = _setup(client)
    key = str(uuid.uuid4())
    body = {
        "spec_revision_id": spec["id"],
        "mode": "TEST",
        "config": CONFIG,
        "fixture_id": "diamond",
    }
    first = client.post("/api/v1/planning-runs", json=body, headers={"Idempotency-Key": key})
    second = client.post("/api/v1/planning-runs", json=body, headers={"Idempotency-Key": key})
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]


def test_unknown_planning_run_returns_404(client) -> None:
    response = client.get("/api/v1/planning-runs/00000000-0000-4000-8000-000000000000")
    assert response.status_code == 404

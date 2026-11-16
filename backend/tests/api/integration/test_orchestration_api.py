"""编排/图校验端点：无效输入仍 200，派生结果为空。"""

from __future__ import annotations

from api_support import create_project, create_spec, diamond_tasks, policy, task


def test_orchestration_returns_derived_fields(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    response = client.post(
        "/api/v1/orchestrations",
        json={"spec_revision_id": spec["id"], "tasks": diamond_tasks()},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["parallel_batches"] == [["A"], ["B", "C"], ["D"]]
    assert body["ordered_task_ids"] == ["A", "B", "C", "D"]
    assert body["validation_report"]["valid"] is True
    assert len(body["input_hash"]) == 64
    assert {stage["stage_id"] for stage in body["execution_stages"]} == {"design", "build"}


def test_invalid_graph_still_returns_200_with_empty_derivation(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    cyclic = [task("A", deps=("B",)), task("B", deps=("A",))]
    response = client.post(
        "/api/v1/orchestrations",
        json={"spec_revision_id": spec["id"], "tasks": cyclic},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["validation_report"]["valid"] is False
    assert body["parallel_batches"] == []
    assert body["edges"] == []
    assert body["validation_report"]["errors"][0]["code"] == "CYCLE"


def test_workflow_validation_returns_report_only(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    response = client.post(
        "/api/v1/workflow-validations",
        json={"spec_revision_id": spec["id"], "tasks": [task("A", deps=("X",))]},
    )
    assert response.status_code == 200
    report = response.json()
    assert report["valid"] is False
    assert report["errors"][0]["code"] == "MISSING_DEPENDENCY"


def test_orchestration_policy_is_applied(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    response = client.post(
        "/api/v1/orchestrations",
        json={
            "spec_revision_id": spec["id"],
            "policy": policy(required_categories=["test"]),
            "tasks": diamond_tasks(),
        },
    )
    assert response.status_code == 200
    assert response.json()["validation_report"]["valid"] is False
    assert "REQUIRED_CATEGORY" in [item["code"] for item in response.json()["validation_report"]["errors"]]


def test_unknown_spec_revision_returns_404(client) -> None:
    response = client.post(
        "/api/v1/orchestrations",
        json={
            "spec_revision_id": "00000000-0000-4000-8000-000000000000",
            "tasks": diamond_tasks(),
        },
    )
    assert response.status_code == 404

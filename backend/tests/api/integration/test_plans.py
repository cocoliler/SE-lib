"""A09/A10：计划版本、来源推导、假设确认、CAS 与不可变性。"""

from __future__ import annotations

import uuid

from api_support import (
    create_plan,
    create_project,
    create_spec,
    diamond_tasks,
    make_planning_run,
    policy,
    spec_content,
    task,
)

LOW = {"id": "AS1", "text": "假设使用现有运行环境", "impact": "low"}
CRITICAL = {"id": "AS9", "text": "假设可以访问外部系统", "impact": "critical"}


def _setup(client):
    project = create_project(client)
    spec = create_spec(client, project["id"])
    run = make_planning_run(client, spec["id"])
    state = client.get(f"/api/v1/planning-runs/{run['id']}").json()
    assert state["status"] == "SUCCEEDED"
    return project, spec, run


def test_plan_from_test_run_keeps_origin(client) -> None:
    project, spec, run = _setup(client)
    response = create_plan(
        client, project["id"], spec["id"], diamond_tasks(), planning_run_id=run["id"]
    )
    assert response.status_code == 201, response.text
    body = response.json()
    revision = body["revision"]
    assert revision["source"] == "TEST"
    assert revision["origin_mode"] == "TEST"
    assert revision["planning_run_id"] == run["id"]
    assert revision["parallel_batches"] == [["A"], ["B", "C"], ["D"]]
    assert revision["validation_report"]["valid"] is True
    assert len(revision["hash"]) == 64


def test_manual_plan_has_no_origin_mode(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    response = create_plan(client, project["id"], spec["id"], diamond_tasks())
    assert response.status_code == 201, response.text
    revision = response.json()["revision"]
    assert revision["source"] == "MANUAL"
    assert revision["origin_mode"] == "NONE"
    assert revision["planning_run_id"] is None


def test_editing_test_candidate_keeps_origin_but_source_manual(client) -> None:
    project, spec, run = _setup(client)
    tasks = diamond_tasks()
    tasks[0]["name"] = "被人工改名的任务"
    response = create_plan(
        client, project["id"], spec["id"], tasks, planning_run_id=run["id"]
    )
    assert response.status_code == 201, response.text
    revision = response.json()["revision"]
    assert revision["source"] == "MANUAL"
    assert revision["origin_mode"] == "TEST"


def test_planning_run_policy_mismatch_blocks_save(client) -> None:
    project, spec, run = _setup(client)
    response = create_plan(
        client,
        project["id"],
        spec["id"],
        diamond_tasks(),
        planning_run_id=run["id"],
        policy=policy(allowed_stages=["design", "build"]),
    )
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "VALIDATION_FAILED"
    assert body["issues"][0]["code"] == "SOURCE_MISMATCH"


def test_planning_run_from_other_project_blocks_save(client) -> None:
    project, spec, _ = _setup(client)
    other_project = create_project(client, "另一个项目")
    other_spec = create_spec(client, other_project["id"])
    other_run = make_planning_run(client, other_spec["id"])

    response = create_plan(
        client, project["id"], spec["id"], diamond_tasks(), planning_run_id=other_run["id"]
    )
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "VALIDATION_FAILED"
    assert body["issues"][0]["code"] == "SOURCE_MISMATCH"


def test_unsucceeded_run_cannot_be_source(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    blocked = make_planning_run(client, spec["id"], fixture="blocked")
    response = create_plan(
        client,
        project["id"],
        spec["id"],
        diamond_tasks(),
        planning_run_id=blocked["id"],
    )
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "VALIDATION_FAILED"
    assert body["issues"][0]["code"] == "SOURCE_MISMATCH"


def test_critical_assumption_blocks_save(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    tasks = [task("A", assumptions=(CRITICAL,))]
    response = create_plan(client, project["id"], spec["id"], tasks)
    assert response.status_code == 422
    codes = [issue["code"] for issue in response.json()["error"]["issues"]]
    assert "CRITICAL_ASSUMPTION" in codes


def test_low_assumption_must_be_confirmed_exactly(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    tasks = [task("A", assumptions=(LOW,))]

    missing = create_plan(client, project["id"], spec["id"], tasks)
    assert missing.status_code == 422
    assert "UNCONFIRMED_ASSUMPTION" in [i["code"] for i in missing.json()["error"]["issues"]]

    extra = create_plan(client, project["id"], spec["id"], tasks, confirmed=["AS1", "AS2"])
    assert extra.status_code == 422

    ok = create_plan(client, project["id"], spec["id"], tasks, confirmed=["AS1"])
    assert ok.status_code == 201, ok.text
    assert ok.json()["revision"]["confirmed_assumption_ids"] == ["AS1"]


def test_duplicate_assumption_id_rejected(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    tasks = [task("A", assumptions=(LOW,)), task("B", deps=("A",), assumptions=(LOW,))]
    response = create_plan(client, project["id"], spec["id"], tasks, confirmed=["AS1"])
    assert response.status_code == 422
    assert response.json()["error"]["issues"][0]["code"] == "DUPLICATE_ID"


def test_invalid_graph_cannot_be_saved(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    cyclic = [task("A", deps=("B",)), task("B", deps=("A",))]
    response = create_plan(client, project["id"], spec["id"], cyclic)
    assert response.status_code == 422
    assert response.json()["error"]["issues"][0]["code"] == "CYCLE"


def test_plan_creation_is_idempotent(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    key = str(uuid.uuid4())
    first = create_plan(client, project["id"], spec["id"], diamond_tasks(), key=key)
    second = create_plan(client, project["id"], spec["id"], diamond_tasks(), key=key)
    assert first.status_code == second.status_code == 201
    assert first.json()["plan_id"] == second.json()["plan_id"]


def test_revision_append_uses_cas_and_keeps_history(client) -> None:
    project, spec, run = _setup(client)
    created = create_plan(
        client, project["id"], spec["id"], diamond_tasks(), planning_run_id=run["id"]
    ).json()
    plan_id = created["plan_id"]
    first_revision = created["revision"]

    edited = diamond_tasks()
    edited[0]["name"] = "改名后的任务"
    appended = client.post(
        f"/api/v1/plans/{plan_id}/revisions",
        json={
            "expected_revision": 1,
            "parent_revision_id": first_revision["id"],
            "spec_revision_id": spec["id"],
            "planning_run_id": run["id"],
            "tasks": edited,
            "confirmed_assumption_ids": [],
        },
    )
    assert appended.status_code == 201, appended.text
    second_revision = appended.json()
    assert second_revision["revision"] == 2
    assert second_revision["parent_revision_id"] == first_revision["id"]
    assert second_revision["source"] == "MANUAL"
    assert second_revision["origin_mode"] == "TEST"

    old = client.get(f"/api/v1/plan-revisions/{first_revision['id']}").json()
    assert old["hash"] == first_revision["hash"]
    assert old["tasks"][0]["name"] != "改名后的任务"

    stale = client.post(
        f"/api/v1/plans/{plan_id}/revisions",
        json={
            "expected_revision": 1,
            "spec_revision_id": spec["id"],
            "tasks": diamond_tasks(),
            "confirmed_assumption_ids": [],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "REVISION_CONFLICT"


def test_parent_revision_must_belong_to_same_plan(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    first_plan = create_plan(client, project["id"], spec["id"], diamond_tasks()).json()
    second_plan = create_plan(client, project["id"], spec["id"], diamond_tasks()).json()

    response = client.post(
        f"/api/v1/plans/{first_plan['plan_id']}/revisions",
        json={
            "expected_revision": 1,
            "parent_revision_id": second_plan["revision"]["id"],
            "spec_revision_id": spec["id"],
            "tasks": diamond_tasks(),
            "confirmed_assumption_ids": [],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["issues"][0]["code"] == "SOURCE_MISMATCH"


def test_revision_list_is_newest_first(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    created = create_plan(client, project["id"], spec["id"], diamond_tasks()).json()
    client.post(
        f"/api/v1/plans/{created['plan_id']}/revisions",
        json={
            "expected_revision": 1,
            "spec_revision_id": spec["id"],
            "tasks": diamond_tasks(),
            "confirmed_assumption_ids": [],
        },
    )
    items = client.get(f"/api/v1/plans/{created['plan_id']}/revisions").json()["items"]
    assert [item["revision"] for item in items] == [2, 1]


def test_spec_revision_from_other_project_rejected(client) -> None:
    project = create_project(client)
    other_project = create_project(client, "另一个项目")
    other_spec = create_spec(client, other_project["id"])
    response = create_plan(client, project["id"], other_spec["id"], diamond_tasks())
    assert response.status_code == 422
    assert response.json()["error"]["issues"][0]["code"] == "SOURCE_MISMATCH"


def test_unknown_plan_returns_404(client) -> None:
    response = client.get("/api/v1/plans/00000000-0000-4000-8000-000000000000/revisions")
    assert response.status_code == 404


def test_unknown_planning_run_returns_404(client) -> None:
    project = create_project(client)
    spec = create_spec(client, project["id"])
    response = create_plan(
        client,
        project["id"],
        spec["id"],
        diamond_tasks(),
        planning_run_id="00000000-0000-4000-8000-000000000000",
    )
    assert response.status_code == 404


def test_plan_snapshot_contains_spec_reference(client) -> None:
    project = create_project(client)
    content = spec_content(product_name="另一份规格")
    spec = create_spec(client, project["id"], content)
    revision = create_plan(client, project["id"], spec["id"], diamond_tasks()).json()["revision"]
    assert revision["spec_revision_id"] == spec["id"]
    assert revision["validation_report"]["input_hash"]

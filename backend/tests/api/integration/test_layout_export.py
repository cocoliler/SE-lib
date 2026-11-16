"""布局独立于计划 hash；导出包含快照。"""

from __future__ import annotations

from api_support import create_plan, create_project, create_spec, diamond_tasks


def _plan(client):
    project = create_project(client)
    spec = create_spec(client, project["id"])
    created = create_plan(client, project["id"], spec["id"], diamond_tasks()).json()
    return project, spec, created


def test_default_layout_is_revision_zero(client) -> None:
    _, _, created = _plan(client)
    revision_id = created["revision"]["id"]
    layout = client.get(f"/api/v1/plan-revisions/{revision_id}/layout").json()
    assert layout["revision"] == 0
    assert layout["positions"] == {}
    assert layout["notes"] == []
    assert layout["viewport"]["zoom"] == 1.0


def test_layout_update_uses_its_own_cas(client) -> None:
    _, _, created = _plan(client)
    revision_id = created["revision"]["id"]
    payload = {
        "expected_revision": 0,
        "positions": {"A": {"x": 10, "y": 20}},
        "notes": [{"id": "note-1", "text": "起始任务", "x": 0, "y": 0}],
        "viewport": {"x": 0, "y": 0, "zoom": 1.2},
    }
    first = client.put(f"/api/v1/plan-revisions/{revision_id}/layout", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["revision"] == 1

    stale = client.put(f"/api/v1/plan-revisions/{revision_id}/layout", json=payload)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "REVISION_CONFLICT"


def test_layout_does_not_change_plan_hash(client) -> None:
    _, _, created = _plan(client)
    revision_id = created["revision"]["id"]
    before = client.get(f"/api/v1/plan-revisions/{revision_id}").json()

    client.put(
        f"/api/v1/plan-revisions/{revision_id}/layout",
        json={
            "expected_revision": 0,
            "positions": {"A": {"x": 1, "y": 2}},
            "notes": [],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    )
    after = client.get(f"/api/v1/plan-revisions/{revision_id}").json()
    assert before["hash"] == after["hash"]


def test_layout_with_unknown_task_rejected(client) -> None:
    _, _, created = _plan(client)
    revision_id = created["revision"]["id"]
    response = client.put(
        f"/api/v1/plan-revisions/{revision_id}/layout",
        json={
            "expected_revision": 0,
            "positions": {"Z": {"x": 1, "y": 2}},
            "notes": [],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["issues"][0]["code"] == "MISSING_INPUT"


def test_layout_rejects_invalid_zoom(client) -> None:
    _, _, created = _plan(client)
    revision_id = created["revision"]["id"]
    response = client.put(
        f"/api/v1/plan-revisions/{revision_id}/layout",
        json={
            "expected_revision": 0,
            "positions": {},
            "notes": [],
            "viewport": {"x": 0, "y": 0, "zoom": 0},
        },
    )
    assert response.status_code == 422


def test_export_contains_snapshots(client) -> None:
    _, spec, created = _plan(client)
    revision_id = created["revision"]["id"]
    response = client.get(f"/api/v1/plan-revisions/{revision_id}/export", params={"format": "json"})
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    bundle = response.json()
    assert bundle["schema_version"] == "1.0"
    assert bundle["spec_snapshot"]["product_name"] == spec["content"]["product_name"]
    assert bundle["plan_revision"]["hash"] == created["revision"]["hash"]
    assert bundle["plan_revision"]["validation_report"]["valid"] is True
    assert bundle["layout"]["revision"] == 0


def test_export_rejects_unknown_format(client) -> None:
    _, _, created = _plan(client)
    response = client.get(
        f"/api/v1/plan-revisions/{created['revision']['id']}/export", params={"format": "yaml"}
    )
    assert response.status_code == 422


def test_export_unknown_revision_returns_404(client) -> None:
    response = client.get(
        "/api/v1/plan-revisions/00000000-0000-4000-8000-000000000000/export"
    )
    assert response.status_code == 404

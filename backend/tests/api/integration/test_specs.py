"""A02/A03：规格版本、CAS、幂等、结构阻断、分页与体积限制。"""

from __future__ import annotations

import uuid

from api_support import create_project, create_spec, requirement, spec_content


def test_create_spec_revision_increments(client) -> None:
    project = create_project(client)
    first = create_spec(client, project["id"], expected=0)
    assert first["revision"] == 1
    assert len(first["hash"]) == 64

    second = create_spec(client, project["id"], expected=1)
    assert second["revision"] == 2
    assert second["spec_id"] == first["spec_id"]
    assert second["id"] != first["id"]


def test_stale_expected_revision_conflicts(client) -> None:
    project = create_project(client)
    create_spec(client, project["id"], expected=0)
    response = client.post(
        f"/api/v1/projects/{project['id']}/spec-revisions",
        json={"expected_revision": 0, "content": spec_content()},
    )
    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "REVISION_CONFLICT"
    assert body["issues"] == []


def test_idempotency_replays_original_result(client) -> None:
    project = create_project(client)
    key = str(uuid.uuid4())
    first = create_spec(client, project["id"], expected=0, key=key)
    second = create_spec(client, project["id"], expected=0, key=key)
    assert first["id"] == second["id"]
    assert second["revision"] == 1


def test_idempotency_key_with_different_body_conflicts(client) -> None:
    project = create_project(client)
    key = str(uuid.uuid4())
    create_spec(client, project["id"], expected=0, key=key)
    response = client.post(
        f"/api/v1/projects/{project['id']}/spec-revisions",
        json={"expected_revision": 0, "content": spec_content(product_name="不同内容")},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_invalid_idempotency_key_rejected(client) -> None:
    project = create_project(client)
    response = client.post(
        f"/api/v1/projects/{project['id']}/spec-revisions",
        json={"expected_revision": 0, "content": spec_content()},
        headers={"Idempotency-Key": "not-a-uuid"},
    )
    assert response.status_code == 422


def test_duplicate_requirement_id_blocks_before_model(client) -> None:
    project = create_project(client)
    content = spec_content(requirements=[requirement("R1"), requirement("R1")])
    response = client.post(
        f"/api/v1/projects/{project['id']}/spec-revisions",
        json={"expected_revision": 0, "content": content},
    )
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "VALIDATION_FAILED"
    assert "重复" in body["message"]


def test_spec_validation_endpoint_is_side_effect_free(client) -> None:
    payload = {"content": spec_content()}
    first = client.post("/api/v1/spec-validations", json=payload)
    second = client.post("/api/v1/spec-validations", json=payload)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["valid"] is True
    assert first.json()["input_hash"] == second.json()["input_hash"]


def test_spec_validation_rejects_invalid_content_at_parse(client) -> None:
    content = spec_content(requirements=[requirement("R1"), requirement("R1")])
    response = client.post("/api/v1/spec-validations", json={"content": content})
    assert response.status_code == 422
    assert "重复" in response.json()["error"]["message"]


def test_unparseable_spec_returns_422(client) -> None:
    response = client.post("/api/v1/spec-validations", json={"content": {"schema_version": "1.0"}})
    assert response.status_code == 422


def test_pagination_returns_cursor(client) -> None:
    project = create_project(client)
    for revision in range(4):
        create_spec(client, project["id"], expected=revision)
    first_page = client.get(
        f"/api/v1/projects/{project['id']}/spec-revisions", params={"limit": 2}
    ).json()
    assert len(first_page["items"]) == 2
    assert first_page["next_cursor"]
    second_page = client.get(
        f"/api/v1/projects/{project['id']}/spec-revisions",
        params={"limit": 2, "cursor": first_page["next_cursor"]},
    ).json()
    assert len(second_page["items"]) == 2
    ids = {item["id"] for item in first_page["items"]} | {item["id"] for item in second_page["items"]}
    assert len(ids) == 4


def test_oversized_body_rejected(client) -> None:
    project = create_project(client)
    huge = "x" * (1024 * 1024 + 10)
    response = client.post(
        f"/api/v1/projects/{project['id']}/spec-revisions",
        json={"expected_revision": 0, "content": {"supplemental_text": huge}},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_unknown_spec_revision_returns_404(client) -> None:
    response = client.get("/api/v1/spec-revisions/00000000-0000-4000-8000-000000000000")
    assert response.status_code == 404

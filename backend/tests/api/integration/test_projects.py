"""A01：项目隔离与基本读写。"""

from __future__ import annotations

from api_support import create_project, create_spec, spec_content


def test_create_and_list_projects(client) -> None:
    project = create_project(client, "项目甲")
    assert project["id"]
    assert project["name"] == "项目甲"
    assert project["archived_at"] is None
    assert project["created_at"].endswith("Z")

    listing = client.get("/api/v1/projects").json()
    assert [item["id"] for item in listing["items"]] == [project["id"]]
    assert listing["next_cursor"] is None


def test_projects_are_isolated(client) -> None:
    first = create_project(client, "项目甲")
    second = create_project(client, "项目乙")

    create_spec(client, first["id"], spec_content(product_name="甲规格"))
    create_spec(client, second["id"], spec_content(product_name="乙规格"))

    first_items = client.get(f"/api/v1/projects/{first['id']}/spec-revisions").json()["items"]
    second_items = client.get(f"/api/v1/projects/{second['id']}/spec-revisions").json()["items"]
    assert len(first_items) == 1 and len(second_items) == 1
    assert first_items[0]["id"] != second_items[0]["id"]

    detail = client.get(f"/api/v1/spec-revisions/{first_items[0]['id']}").json()
    assert detail["content"]["product_name"] == "甲规格"


def test_empty_name_rejected(client) -> None:
    response = client.post("/api/v1/projects", json={"name": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_unknown_project_returns_404(client) -> None:
    response = client.get("/api/v1/projects/00000000-0000-4000-8000-000000000000/spec-revisions")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_new_project_has_no_specs(client) -> None:
    project = create_project(client, "空项目")
    listing = client.get(f"/api/v1/projects/{project['id']}/spec-revisions").json()
    assert listing == {"items": [], "next_cursor": None}

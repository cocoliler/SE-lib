"""Alembic 启动路径：空库升级后 13 张表齐备且可读写。"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app
from api_support import make_settings

EXPECTED_TABLES = {
    "projects",
    "specs",
    "spec_revisions",
    "planning_runs",
    "planning_attempts",
    "plans",
    "plan_revisions",
    "tasks",
    "task_dependencies",
    "task_details",
    "plan_derivations",
    "layouts",
    "commands",
}


def test_alembic_startup_creates_schema(tmp_path, stub_engine) -> None:
    settings = make_settings(tmp_path, use_alembic=True)
    app = create_app(settings, stub_engine)
    with TestClient(app) as client:
        assert client.app.state.schema_mode == "alembic"
        project = client.post("/api/v1/projects", json={"name": "迁移项目"}).json()
        assert project["id"]

    database_path = settings.data_dir / "flowstudio.db"
    connection = sqlite3.connect(database_path)
    try:
        names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        connection.close()

    assert EXPECTED_TABLES <= names
    assert "alembic_version" in names

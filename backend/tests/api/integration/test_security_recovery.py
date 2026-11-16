"""本地安全边界（Host/Origin）与重启恢复。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from flowstudio_contracts import DesignSpecContent, PlanningConfig, PlanningMode

from app.config import Settings
from app.main import create_app
from app.persistence import build_sessionmaker, create_engine_for
from app.persistence import repos
from app.persistence.lock import InstanceLock
from app.persistence.tables import Base
from api_support import make_settings, spec_content


def test_bad_host_is_rejected(client) -> None:
    response = client.get("/api/v1/projects", headers={"Host": "evil.example"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_FORBIDDEN"


def test_bad_origin_is_rejected(client) -> None:
    response = client.get("/api/v1/projects", headers={"Origin": "http://evil.example"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_FORBIDDEN"


def test_state_reports_schema_mode_and_queue(client) -> None:
    assert client.app.state.schema_mode in {"create_all", "alembic"}
    assert client.app.state.settings.queue_capacity == 10


def test_instance_lock_rejects_second_holder(tmp_path) -> None:
    first = InstanceLock(tmp_path / "instance.lock")
    second = InstanceLock(tmp_path / "instance.lock")
    first.acquire()
    try:
        with pytest.raises(RuntimeError):
            second.acquire()
    finally:
        first.release()
    # 释放后可以再次获取
    third = InstanceLock(tmp_path / "instance.lock")
    third.acquire()
    third.release()


def test_restart_marks_unfinished_run_failed_and_keeps_history(tmp_path, stub_engine) -> None:
    settings: Settings = make_settings(tmp_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine_for(settings.database_url)
    Base.metadata.create_all(engine)
    sessionmaker = build_sessionmaker(engine)
    with sessionmaker() as session:
        project = repos.create_project(session, "项目甲")
        revision = repos.create_spec_revision(
            session,
            str(project.id),
            0,
            DesignSpecContent.model_validate(spec_content()),
            "0" * 64,
        )
        run = repos.create_planning_run(
            session,
            str(revision.id),
            PlanningMode.TEST,
            PlanningConfig(model="deepseek-chat", granularity="standard", planning_constraints=[]),
            "diamond",
        )
        session.commit()
        project_id = str(project.id)
        run_id = run.id
    engine.dispose()

    app = create_app(settings, stub_engine)
    with TestClient(app) as client:
        run_body = client.get(f"/api/v1/planning-runs/{run_id}").json()
        assert run_body["status"] == "FAILED"
        assert run_body["error"]["code"] == "PROCESS_INTERRUPTED"

        history = client.get(f"/api/v1/projects/{project_id}/spec-revisions").json()
        assert len(history["items"]) == 1

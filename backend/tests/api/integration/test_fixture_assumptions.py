"""经由 TEST 公开接口核对关键假设、持久化结果和旧运行的轮询。"""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from api_support import create_project, create_spec, make_planning_run, task
from app.main import create_app
from app.persistence.tables import PlanningRunRow
from flowstudio_contracts.base import BodyText
from flowstudio_contracts.constants import MAX_BLOCKING_QUESTIONS


def critical_fixture(questions):
    assumption = {"id": "approval", "impact": "critical", "text": "预约是否需要审批？"}
    return {
        "schema_version": "1.0",
        "tasks": [task("A", assumptions=(assumption,))],
        "blocking_questions": questions,
    }


@pytest.mark.parametrize("case", ["critical_only", "existing_question", "capacity_exhausted"])
def test_fixture_poll_returns_readable_terminal_result(settings, case):
    questions = []
    if case == "existing_question":
        questions = ["需要在哪个时区处理？"]
    elif case == "capacity_exhausted":
        length = TypeAdapter(BodyText).json_schema()["maxLength"]
        questions = [str(i).ljust(length, "问") for i in range(MAX_BLOCKING_QUESTIONS)]

    settings.fixtures_dir.mkdir()
    payload = critical_fixture(questions)
    (settings.fixtures_dir / "review.json").write_text(json.dumps(payload), encoding="utf-8")
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        spec = create_spec(client, create_project(client)["id"])
        created = make_planning_run(client, spec["id"], fixture="review")
        response = client.get(created["poll_url"])
        assert response.status_code == 200, response.text
        run = response.json()
        assert run["attempt_count"] == 1
        assert client.get(created["poll_url"] + "/tasks").status_code == 409
        if case == "capacity_exhausted":
            assert run["status"] == "FAILED"
            assert run["error"]["code"] == "MODEL_SCHEMA"
        else:
            assert run["status"] == "NEEDS_INPUT"
            proposal = run["proposal"]
            assert proposal["tasks"] == payload["tasks"]
            assert proposal["blocking_questions"][:len(questions)] == questions
            assert any("approval" in q and "预约是否需要审批" in q for q in proposal["blocking_questions"])
            with app.state.sessionmaker() as session:
                stored = session.get(PlanningRunRow, created["id"])
                assert json.loads(stored.proposal_json) == proposal


def test_poll_previous_critical_only_fixture(app):
    with TestClient(app, raise_server_exceptions=False) as reader:
        spec = create_spec(reader, create_project(reader)["id"])
        created = make_planning_run(reader, spec["id"], fixture="blocked")
        # 历史版本写入了合法候选，但 NEEDS_INPUT 记录缺少问句。
        with app.state.sessionmaker() as session:
            row = session.get(PlanningRunRow, created["id"])
            row.proposal_json = json.dumps(critical_fixture([]))
            session.commit()
        response = reader.get(created["poll_url"])
        assert response.status_code == 200, response.text
        run = response.json()
        assert run["status"] == "NEEDS_INPUT"
        assert any("预约是否需要审批" in q for q in run["proposal"]["blocking_questions"])

"""pytest 支撑：抽象规格/任务构造器与可注入的假规划引擎（不依赖产品案例）。

类型全部来自 `flowstudio_contracts`，测试不再维护第二套模型。
"""

from __future__ import annotations

from pathlib import Path

from flowstudio_contracts import (
    PlanningMode,
    RunError,
    RunFailureCode,
    TaskProposal,
    sha256_hex,
)

from app.config import Settings
from app.providers.base import AttemptRecord, PlanningOutcome


def make_settings(tmp_path: Path, **overrides) -> Settings:
    data_dir = tmp_path / "data"
    base = Settings(
        data_dir=data_dir,
        database_url=f"sqlite:///{(data_dir / 'flowstudio.db').as_posix()}",
        use_alembic=False,
        instance_lock=False,
        worker_mode="inline",
        fixtures_dir=tmp_path / "fixtures",
        queue_capacity=10,
        allowed_hosts=("127.0.0.1", "localhost", "testserver"),
        allowed_origins=("http://127.0.0.1:5173", "http://localhost:5173"),
    )
    return base.with_overrides(**overrides) if overrides else base


class StubEngine:
    """按 fixture_id 返回预置 TaskProposal；REAL 一律未配置。"""

    def __init__(self, proposals: dict[str, dict] | None = None) -> None:
        self.proposals = proposals or {}

    def fixtures(self) -> tuple[str, ...]:
        return tuple(sorted(self.proposals))

    def plan(self, *, mode, spec_revision, config, fixture_id, run_id):  # noqa: ANN001
        if mode is PlanningMode.TEST:
            proposal = TaskProposal.model_validate(self.proposals[fixture_id or ""])
            return PlanningOutcome(
                proposal=proposal,
                usage=None,
                attempts=[
                    AttemptRecord(
                        attempt_no=1,
                        request_hash=sha256_hex({"run": run_id}),
                        response=proposal.model_dump(mode="json", by_alias=True),
                        usage={"total_tokens": 0},
                    )
                ],
            )
        return PlanningOutcome(
            error=RunError(
                code=RunFailureCode.MODEL_AUTH,
                message="no adapter",
                retryable=False,
            ),
            attempts=[
                AttemptRecord(attempt_no=1, request_hash="", error={"code": "MODEL_AUTH"})
            ],
        )


# --------------------------------------------------------------------------- 构造器


def requirement(
    rid: str = "R1",
    priority: str = "must",
    kind: str = "functional",
    text: str = "用户可以完成主要操作",
    acceptance: tuple[str, ...] = ("可以观察的结果",),
) -> dict:
    return {
        "id": rid,
        "kind": kind,
        "text": text,
        "priority": priority,
        "acceptance_criteria": list(acceptance),
    }


def spec_content(requirements: list[dict] | None = None, **overrides) -> dict:
    payload = {
        "schema_version": "1.0",
        "product_name": "抽象示例",
        "background": "用于结构测试的中性背景，不指向任何具体产品。",
        "goals": ["支持一个可验收的目标"],
        "target_users": ["使用者"],
        "requirements": requirements
        or [
            requirement(),
            requirement("R2", "should", text="次要需求"),
            requirement("N1", "could", "nonfunctional", text="性能要求"),
        ],
        "technical_constraints": [],
        "development_constraints": [],
        "delivery_requirements": ["交付可运行原型"],
        "acceptance_criteria": ["关键路径可用"],
        "supplemental_text": "",
        "confirmed_assumptions": [],
    }
    payload.update(overrides)
    return payload


def task(
    task_id: str,
    *,
    deps: tuple[str, ...] = (),
    reqs: tuple[str, ...] = ("R1",),
    inputs: tuple[dict, ...] = (),
    stage: str = "design",
    category: str = "design",
    role: str = "architect",
    deliverable: tuple[str, ...] = ("doc",),
    assumptions: tuple[dict, ...] = (),
    name: str | None = None,
) -> dict:
    return {
        "task_id": task_id,
        "name": name or f"任务 {task_id}",
        "description": f"完成 {task_id} 的交付",
        "category": category,
        "stage": stage,
        "priority": "medium",
        "assigned_role": role,
        "dependencies": list(deps),
        "inputs": list(inputs),
        "deliverables": [{"id": item, "text": f"{task_id} 的 {item}"} for item in deliverable],
        "acceptance_criteria": ["结果可观察"],
        "source_requirement_ids": list(reqs),
        "rationale": "",
        "assumptions": list(assumptions),
        "estimated_effort": None,
    }


def input_spec(rid: str = "R1") -> dict:
    return {"kind": "spec", "requirement_id": rid}

def input_task(task_id: str, deliverable_id: str = "doc") -> dict:
    return {"kind": "task", "task_id": task_id, "deliverable_id": deliverable_id}


def policy(**overrides) -> dict:
    """契约 PlanningPolicy 的完整字段（缺省全部不额外限制）。"""
    payload = {
        "schema_version": "1.0",
        "rules_version": "1.0",
        "allowed_stages": None,
        "allowed_roles": None,
        "allowed_categories": None,
        "allowed_stage_edges": None,
        "required_categories": [],
    }
    payload.update(overrides)
    return payload


def diamond_tasks() -> list[dict]:
    return [
        task("A", reqs=("R1", "R2")),
        task("B", deps=("A",), inputs=(input_task("A"),)),
        task("C", deps=("A",), inputs=(input_task("A"),)),
        task(
            "D",
            deps=("B", "C"),
            inputs=(input_task("B"), input_task("C")),
            stage="build",
            category="build",
            role="engineer",
        ),
    ]


def default_proposals() -> dict[str, dict]:
    return {
        "diamond": {
            "schema_version": "1.0",
            "tasks": diamond_tasks(),
            "blocking_questions": [],
        },
        "blocked": {
            "schema_version": "1.0",
            "tasks": [],
            "blocking_questions": ["需要确认是否允许完全离线运行"],
        },
    }


# --------------------------------------------------------------------------- HTTP 辅助


def create_project(client, name: str = "项目甲") -> dict:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def create_spec(client, project_id: str, content: dict | None = None, expected: int = 0,
                key: str | None = None) -> dict:
    headers = {"Idempotency-Key": key} if key else {}
    response = client.post(
        f"/api/v1/projects/{project_id}/spec-revisions",
        json={"expected_revision": expected, "content": content or spec_content()},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_planning_run(client, spec_revision_id: str, fixture: str = "diamond") -> dict:
    response = client.post(
        "/api/v1/planning-runs",
        json={
            "spec_revision_id": spec_revision_id,
            "mode": "TEST",
            "config": {"model": "configured-default", "granularity": "standard",
                       "planning_constraints": []},
            "fixture_id": fixture,
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def create_plan(client, project_id: str, spec_revision_id: str, tasks: list[dict],
                planning_run_id: str | None = None, confirmed: list[str] | None = None,
                policy: dict | None = None, key: str | None = None):
    body = {
        "spec_revision_id": spec_revision_id,
        "tasks": tasks,
        "confirmed_assumption_ids": confirmed or [],
    }
    if planning_run_id:
        body["planning_run_id"] = planning_run_id
    if policy is not None:
        body["policy"] = policy
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(
        f"/api/v1/projects/{project_id}/plans", json=body, headers=headers
    )

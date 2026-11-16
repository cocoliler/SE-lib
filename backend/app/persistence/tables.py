"""SQLite 表定义（13 组，对应 v3.1 数据库设计）。

约定：UUID 存 TEXT；时间存 UTC RFC3339 文本；业务 JSON 存规范化文本列。
任务与依赖单独关系表，用复合 FK 保证不能跨版本引用。
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    archived_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class SpecRow(Base):
    __tablename__ = "specs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    latest_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SpecRevisionRow(Base):
    __tablename__ = "spec_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    spec_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("specs.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (
        UniqueConstraint("spec_id", "revision", name="uq_spec_revision"),
        Index("ix_spec_revisions_spec_created", "spec_id", "created_at"),
    )


class PlanningRunRow(Base):
    __tablename__ = "planning_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','NEEDS_INPUT','FAILED')",
            name="ck_planning_status",
        ),
        CheckConstraint("mode IN ('REAL','TEST')", name="ck_planning_mode"),
        Index("ix_planning_runs_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    spec_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("spec_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    fixture_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    proposal_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class PlanningAttemptRow(Base):
    __tablename__ = "planning_attempts"

    planning_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("planning_runs.id", ondelete="CASCADE"), primary_key=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class PlanRow(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    latest_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PlanRevisionRow(Base):
    __tablename__ = "plan_revisions"
    __table_args__ = (
        UniqueConstraint("plan_id", "revision", name="uq_plan_revision"),
        Index("ix_plan_revisions_plan_created", "plan_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    spec_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("spec_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    planning_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("planning_runs.id", ondelete="SET NULL"), nullable=True
    )
    parent_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("plan_revisions.id", ondelete="SET NULL"), nullable=True
    )
    policy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    origin_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    confirmed_assumption_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class TaskRow(Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_revision_stage", "revision_id", "stage"),)

    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("plan_revisions.id", ondelete="CASCADE"), primary_key=True
    )
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    assigned_role: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    effort_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaskDependencyRow(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "source_task_id"],
            ["tasks.revision_id", "tasks.task_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["revision_id", "target_task_id"],
            ["tasks.revision_id", "tasks.task_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("source_task_id <> target_task_id", name="ck_dependency_no_self"),
    )

    revision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_task_id: Mapped[str] = mapped_column(String(64), primary_key=True)


class TaskDetailRow(Base):
    __tablename__ = "task_details"
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "task_id"],
            ["tasks.revision_id", "tasks.task_id"],
            ondelete="CASCADE",
        ),
    )

    revision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    inputs_json: Mapped[str] = mapped_column(Text, nullable=False)
    deliverables_json: Mapped[str] = mapped_column(Text, nullable=False)
    acceptance_json: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    assumptions_json: Mapped[str] = mapped_column(Text, nullable=False)


class PlanDerivationRow(Base):
    __tablename__ = "plan_derivations"

    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("plan_revisions.id", ondelete="CASCADE"), primary_key=True
    )
    stages_json: Mapped[str] = mapped_column(Text, nullable=False)
    batches_json: Mapped[str] = mapped_column(Text, nullable=False)
    order_json: Mapped[str] = mapped_column(Text, nullable=False)
    report_json: Mapped[str] = mapped_column(Text, nullable=False)
    rules_version: Mapped[str] = mapped_column(String(20), nullable=False)


class LayoutRow(Base):
    __tablename__ = "layouts"

    plan_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("plan_revisions.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    positions_json: Mapped[str] = mapped_column(Text, nullable=False)
    notes_json: Mapped[str] = mapped_column(Text, nullable=False)
    viewport_json: Mapped[str] = mapped_column(Text, nullable=False)


class CommandRow(Base):
    __tablename__ = "commands"

    scope: Mapped[str] = mapped_column(String(200), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

"""T05 确定性编排器（D 负责）：结构校验 → Kahn 分层 → 阶段分组 → 报告。

纯函数边界：不导入 FastAPI、ORM 或任何 LLM SDK，不读写数据库，不调用模型。
调用方（应用层）负责把 `spec_revision_id` 解析成已保存的 `DesignSpecContent`，
再把结果冻结进 `PlanRevision`；布局、坐标与视口不参与本模块任何计算。

对外契约（与 `tech/artifacts/openapi.json` 的 /orchestrations、/workflow-validations 对齐）：
- `build_plan(tasks, spec, policy)` → `PlanDerivation`；输入非法时派生字段为空、
  `validation_report.valid=false`，仍是 200 响应而不是异常。
- `validate_workflow(tasks, spec, policy)` → `ValidationReport`；复用同一份实现，
  不复制规则。
- 超出 100 任务 / 1000 依赖的保护边界时抛 `OrchestrationLimitError`，由 API 层
  映射为 422；这部分没有合适的 IssueCode，不能用错误码硬凑报告。

已知契约缺口（需契约所有者确认后补码，本模块不自造码）：
- 需求优先级为 should/could 且未被引用时，设计只要求 warning，但 `IssueCode`
  中只有 `POSSIBLE_DUPLICATE`/`ORPHAN` 允许 warning，其余码会被 `Issue` 校验器
  强制为 error。当前实现只把这些需求放进 `coverage.uncovered_ids`，不伪造 warning。
"""

from __future__ import annotations

from collections.abc import Sequence

from flowstudio_contracts import (
    DesignSpecContent,
    Issue,
    IssueCode,
    IssueSeverity,
    PlanningPolicy,
    RULES_VERSION,
    Task,
    TaskEdge,
    sha256_hex,
)
from flowstudio_contracts.constants import MAX_EDGES, MAX_TASKS
from flowstudio_contracts.validation import Coverage
from flowstudio_contracts.workflow import PlanDerivation, ValidationReport

from .graph import find_cycles, group_stages, kahn_batches, scan_dependencies
from .issues import issue, task_path
from .rules import ADVISORY_RULES, COVERAGE_RULES, STRUCTURAL_RULES, RuleContext


class OrchestrationInputError(ValueError):
    """调用方传入不符合编排器前提的输入；应用层应映射为 422 VALIDATION_FAILED。"""


class OrchestrationLimitError(OrchestrationInputError):
    """超出 P0 支持规模（100 任务 / 1000 依赖）的保护边界。"""

    def __init__(self, message: str, *, limit: int, actual: int) -> None:
        super().__init__(message)
        self.limit = limit
        self.actual = actual


def duplicate_task_ids(tasks: Sequence[Task]) -> list[Issue]:
    """task_id 在同一计划内唯一；重复时无法建立可靠映射，必须先修。"""
    seen: dict[str, int] = {}
    issues: list[Issue] = []
    for index, task in enumerate(tasks):
        if task.task_id not in seen:
            seen[task.task_id] = index
            continue
        issues.append(
            issue(
                IssueCode.DUPLICATE_ID,
                task_path(index, "task_id"),
                f"task_id {task.task_id} 与第 {seen[task.task_id]} 项任务重复",
                task_ids=[task.task_id],
                suggestion="重命名该任务并同步更新所有依赖与输入引用",
            )
        )
    return issues


def compute_coverage(tasks: Sequence[Task], spec: DesignSpecContent) -> Coverage:
    """按规格顺序给出已引用/未引用需求；引用只表示"已关联"。"""
    referenced = {requirement_id for task in tasks for requirement_id in task.source_requirement_ids}
    return Coverage(
        covered_ids=[requirement.id for requirement in spec.requirements if requirement.id in referenced],
        uncovered_ids=[
            requirement.id for requirement in spec.requirements if requirement.id not in referenced
        ],
    )


def compute_input_hash(
    tasks: Sequence[Task], spec: DesignSpecContent, policy: PlanningPolicy | None
) -> str:
    """绑定报告与输入的规范化 SHA-256。

    包含规格内容、任务、规划约束快照和规则版本；不含数据库 ID、时间、布局和运行信息，
    因此同一输入永远得到同一 hash，任何影响结果的变化都会改变它。
    """
    return sha256_hex(
        {
            "spec": spec.model_dump(mode="json", by_alias=True),
            "tasks": [task.model_dump(mode="json", by_alias=True) for task in tasks],
            "policy": None if policy is None else policy.model_dump(mode="json", by_alias=True),
            "rules_version": RULES_VERSION,
        }
    )


def validate_workflow(
    tasks: Sequence[Task],
    spec: DesignSpecContent,
    policy: PlanningPolicy | None = None,
) -> ValidationReport:
    """只返回校验报告；与 build_plan 共用同一实现。"""
    report, _ = evaluate(tasks, spec, policy)
    return report


def build_plan(
    tasks: Sequence[Task],
    spec: DesignSpecContent,
    policy: PlanningPolicy | None = None,
) -> PlanDerivation:
    """校验并派生计划；报告不通过时返回空派生结果（供 200 + valid=false）。"""
    report, derivation = evaluate(tasks, spec, policy)
    if derivation is not None:
        return derivation
    return PlanDerivation(
        input_hash=report.input_hash,
        edges=[],
        execution_stages=[],
        parallel_batches=[],
        ordered_task_ids=[],
        validation_report=report,
    )


def evaluate(
    tasks: Sequence[Task],
    spec: DesignSpecContent,
    policy: PlanningPolicy | None,
) -> tuple[ValidationReport, PlanDerivation | None]:
    """一次完整计算：报告始终返回，派生结果只在报告通过时给出。"""
    ordered_tasks: tuple[Task, ...] = tuple(tasks)
    _guard_sizes(ordered_tasks)
    digest = compute_input_hash(ordered_tasks, spec, policy)
    coverage = compute_coverage(ordered_tasks, spec)

    duplicate_issues = duplicate_task_ids(ordered_tasks)
    if duplicate_issues:
        return _report(duplicate_issues, (), coverage, digest), None

    task_by_id = {task.task_id: task for task in ordered_tasks}
    scan = scan_dependencies(ordered_tasks)
    context = RuleContext(
        tasks=ordered_tasks,
        task_by_id=task_by_id,
        requirements=tuple(spec.requirements),
        policy=policy,
        scan=scan,
    )

    structural = [item for rule in STRUCTURAL_RULES for item in rule.check(context)]
    if structural:
        return _report(structural, (), coverage, digest), None

    batches, processed = kahn_batches(tuple(task_by_id), scan.children)
    if processed != len(ordered_tasks):
        # Kahn 无法区分"环上节点"与"环的下游"，必须回到 DFS 取真实环。
        cycles = find_cycles(tuple(task_by_id), scan.children)
        if not cycles:
            raise RuntimeError("编排内部错误：存在未处理任务但未能定位环")
        return _report([_cycle_issue(cycle) for cycle in cycles], (), coverage, digest), None

    late = [item for rule in (*COVERAGE_RULES, *ADVISORY_RULES) for item in rule.check(context)]
    errors = [item for item in late if item.severity is IssueSeverity.ERROR]
    warnings = [item for item in late if item.severity is IssueSeverity.WARNING]
    report = _report(errors, warnings, coverage, digest)
    if errors:
        return report, None

    derivation = PlanDerivation(
        input_hash=digest,
        edges=list(scan.edges),
        execution_stages=group_stages(ordered_tasks, batches),
        parallel_batches=batches,
        ordered_task_ids=[task_id for batch in batches for task_id in batch],
        validation_report=report,
    )
    return report, derivation


def _report(
    errors: Sequence[Issue],
    warnings: Sequence[Issue],
    coverage: Coverage,
    digest: str,
) -> ValidationReport:
    return ValidationReport(
        valid=not errors,
        errors=list(errors),
        warnings=list(warnings),
        coverage=coverage,
        rules_version=RULES_VERSION,
        input_hash=digest,
    )


def _cycle_issue(cycle: Sequence[str]) -> Issue:
    nodes = list(cycle[:-1])
    edges = [
        TaskEdge(source=cycle[index], target=cycle[index + 1]) for index in range(len(cycle) - 1)
    ]
    return issue(
        IssueCode.CYCLE,
        "/tasks",
        "循环依赖：" + " → ".join(cycle),
        task_ids=nodes,
        edges=edges,
        suggestion="移除或调整环上的依赖后重新编排；未处理集合中的环下游任务不算环上节点",
    )


def _guard_sizes(tasks: Sequence[Task]) -> None:
    if not tasks:
        raise OrchestrationInputError(
            "至少需要一项任务；空计划由 API 契约（tasks.min_length=1）在进入编排前拒绝"
        )
    if len(tasks) > MAX_TASKS:
        raise OrchestrationLimitError(
            f"任务数 {len(tasks)} 超过上限 {MAX_TASKS}", limit=MAX_TASKS, actual=len(tasks)
        )
    declared_edges = sum(len(task.dependencies) for task in tasks)
    if declared_edges > MAX_EDGES:
        raise OrchestrationLimitError(
            f"依赖声明 {declared_edges} 条超过上限 {MAX_EDGES}",
            limit=MAX_EDGES,
            actual=declared_edges,
        )


__all__ = [
    "OrchestrationInputError",
    "OrchestrationLimitError",
    "build_plan",
    "compute_coverage",
    "compute_input_hash",
    "duplicate_task_ids",
    "evaluate",
    "validate_workflow",
]

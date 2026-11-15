"""版本化纯函数规则注册表。

每条规则只做一件事，输入 `RuleContext`、输出 `Issue` 列表，不读库、不调模型。
注册表按阶段划分，顺序即报告顺序：
1. STRUCTURAL_RULES：结构、引用、策略约束。任一条失败则不再计算批次。
2. COVERAGE_RULES：需求覆盖与必需类别。图合法才检查，失败仍阻断保存。
3. ADVISORY_RULES：孤立任务与精确重复，只给 warning，不阻断保存。

规则版本随 `rules_version` 写入报告，旧报告不能作为新输入的保存凭证。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from flowstudio_contracts import (
    AssumptionImpact,
    Issue,
    IssueCode,
    IssueSeverity,
    PlanningPolicy,
    Requirement,
    RequirementPriority,
    RULES_VERSION,
    Task,
    TaskEdge,
)

from .graph import DependencyScan
from .issues import issue, normalize_text, pointer, task_path


@dataclass(frozen=True)
class RuleContext:
    """一次校验的只读上下文；由引擎构造，规则不得修改任务或图。"""

    tasks: tuple[Task, ...]
    task_by_id: Mapping[str, Task]
    requirements: tuple[Requirement, ...]
    policy: PlanningPolicy | None
    scan: DependencyScan

    @property
    def requirement_ids(self) -> frozenset[str]:
        return frozenset(requirement.id for requirement in self.requirements)


@dataclass(frozen=True)
class Rule:
    rule_id: str
    version: str
    severity: IssueSeverity
    check: Callable[[RuleContext], list[Issue]]


def _empty_allowlist(ctx: RuleContext, name: str) -> bool:
    """显式空数组表示"不允许任何值"，由 policy-satisfiable 统一报告。"""
    policy = ctx.policy
    return policy is not None and getattr(policy, name) == []


def policy_satisfiable(ctx: RuleContext) -> list[Issue]:
    policy = ctx.policy
    if policy is None:
        return []
    issues: list[Issue] = []
    for name, label in (
        ("allowed_stages", "阶段"),
        ("allowed_roles", "角色"),
        ("allowed_categories", "类别"),
    ):
        if getattr(policy, name) == []:
            issues.append(
                issue(
                    IssueCode.POLICY_UNSATISFIABLE,
                    pointer("policy", name),
                    f"规划约束把{label}允许集合设为空数组，任何任务都无法满足",
                    suggestion="移除该限制或给出至少一个允许值后重新规划",
                )
            )
    return issues


def stage_allowed(ctx: RuleContext) -> list[Issue]:
    if ctx.policy is None or ctx.policy.allowed_stages is None or _empty_allowlist(ctx, "allowed_stages"):
        return []
    allowed = set(ctx.policy.allowed_stages)
    return [
        issue(
            IssueCode.INVALID_STAGE,
            task_path(index, "stage"),
            f"任务阶段 {task.stage} 不在允许集合 {sorted(allowed)} 中",
            task_ids=[task.task_id],
            suggestion="修改任务阶段或调整规划约束，不要编造未注册的阶段",
        )
        for index, task in enumerate(ctx.tasks)
        if task.stage not in allowed
    ]


def role_allowed(ctx: RuleContext) -> list[Issue]:
    if ctx.policy is None or ctx.policy.allowed_roles is None or _empty_allowlist(ctx, "allowed_roles"):
        return []
    allowed = set(ctx.policy.allowed_roles)
    return [
        issue(
            IssueCode.INVALID_ROLE,
            task_path(index, "assigned_role"),
            f"建议角色 {task.assigned_role} 不在允许集合 {sorted(allowed)} 中",
            task_ids=[task.task_id],
            suggestion="修改建议角色或调整规划约束",
        )
        for index, task in enumerate(ctx.tasks)
        if task.assigned_role not in allowed
    ]


def category_allowed(ctx: RuleContext) -> list[Issue]:
    if ctx.policy is None or ctx.policy.allowed_categories is None or _empty_allowlist(ctx, "allowed_categories"):
        return []
    allowed = set(ctx.policy.allowed_categories)
    return [
        issue(
            IssueCode.INVALID_CATEGORY,
            task_path(index, "category"),
            f"任务类别 {task.category} 不在允许集合 {sorted(allowed)} 中",
            task_ids=[task.task_id],
            suggestion="修改任务类别或调整规划约束",
        )
        for index, task in enumerate(ctx.tasks)
        if task.category not in allowed
    ]


def stage_edge_allowed(ctx: RuleContext) -> list[Issue]:
    """同阶段依赖始终允许；跨阶段仅在显式给出 allowed_stage_edges 时检查。"""
    if ctx.policy is None or ctx.policy.allowed_stage_edges is None:
        return []
    allowed = {(edge.from_stage, edge.to_stage) for edge in ctx.policy.allowed_stage_edges}
    issues: list[Issue] = []
    for index, task in enumerate(ctx.tasks):
        for position, dependency in enumerate(task.dependencies):
            source = ctx.task_by_id.get(dependency)
            if source is None or source.task_id == task.task_id or source.stage == task.stage:
                continue
            if (source.stage, task.stage) in allowed:
                continue
            issues.append(
                issue(
                    IssueCode.STAGE_EDGE_FORBIDDEN,
                    task_path(index, "dependencies", position),
                    f"依赖 {dependency}({source.stage}) → {task.task_id}({task.stage}) 不在允许的阶段迁移中",
                    task_ids=[dependency, task.task_id],
                    edges=[TaskEdge(source=dependency, target=task.task_id)],
                    suggestion="调整依赖或阶段；不能用布局位置掩盖非法迁移",
                )
            )
    return issues


def dependency_shape(ctx: RuleContext) -> list[Issue]:
    """缺失/自环/重复依赖在扫描阶段已定位，这里原样复用，避免两套判断。"""
    return list(ctx.scan.issues)


def requirement_refs(ctx: RuleContext) -> list[Issue]:
    known = ctx.requirement_ids
    issues: list[Issue] = []
    for index, task in enumerate(ctx.tasks):
        for position, requirement_id in enumerate(task.source_requirement_ids):
            if requirement_id in known:
                continue
            issues.append(
                issue(
                    IssueCode.UNKNOWN_REQUIREMENT,
                    task_path(index, "source_requirement_ids", position),
                    f"任务 {task.task_id} 引用的需求 {requirement_id} 不在来源规格中",
                    task_ids=[task.task_id],
                    suggestion="改为来源规格中存在的需求 ID，不要引用已删除或未定义的条目",
                )
            )
        for position, reference in enumerate(task.inputs):
            if reference.kind != "spec" or reference.requirement_id in known:
                continue
            issues.append(
                issue(
                    IssueCode.UNKNOWN_REQUIREMENT,
                    task_path(index, "inputs", position, "requirement_id"),
                    f"输入引用的需求 {reference.requirement_id} 不在来源规格中",
                    task_ids=[task.task_id],
                    suggestion="选择来源规格中存在的需求 ID",
                )
            )
    return issues


def input_dependency(ctx: RuleContext) -> list[Issue]:
    issues: list[Issue] = []
    for index, task in enumerate(ctx.tasks):
        dependencies = set(task.dependencies)
        for position, reference in enumerate(task.inputs):
            if reference.kind != "task":
                continue
            path = task_path(index, "inputs", position)
            if reference.task_id == task.task_id or reference.task_id not in ctx.task_by_id:
                issues.append(
                    issue(
                        IssueCode.INPUT_NOT_DEPENDENCY,
                        path,
                        f"输入引用的任务 {reference.task_id} 不存在，无法作为直接上游",
                        task_ids=[task.task_id],
                        suggestion="先建立该任务，再把它加入直接依赖",
                    )
                )
                continue
            if reference.task_id not in dependencies:
                issues.append(
                    issue(
                        IssueCode.INPUT_NOT_DEPENDENCY,
                        path,
                        f"任务 {task.task_id} 读取 {reference.task_id} 的成果但没有直接依赖它",
                        task_ids=[task.task_id, reference.task_id],
                        suggestion="原子地补上直接依赖并重新校验；仅有祖先关系不足以取值",
                    )
                )
    return issues


def input_deliverable(ctx: RuleContext) -> list[Issue]:
    issues: list[Issue] = []
    for index, task in enumerate(ctx.tasks):
        dependencies = set(task.dependencies)
        for position, reference in enumerate(task.inputs):
            if reference.kind != "task" or reference.task_id not in dependencies:
                continue
            producer = ctx.task_by_id.get(reference.task_id)
            if producer is None:
                continue
            if any(deliverable.id == reference.deliverable_id for deliverable in producer.deliverables):
                continue
            issues.append(
                issue(
                    IssueCode.MISSING_INPUT,
                    task_path(index, "inputs", position, "deliverable_id"),
                    f"上游 {reference.task_id} 没有交付 {reference.deliverable_id}",
                    task_ids=[task.task_id, reference.task_id],
                    suggestion="选择上游已声明的交付 ID，或先在上游补充该交付",
                )
            )
    return issues


def assumption_unique(ctx: RuleContext) -> list[Issue]:
    """契约只保证任务内唯一；整个计划内唯一由编排器负责。

    契约没有"假设 ID 重复"专用码，复用通用的 DUPLICATE_ID 并指向
    `/tasks/{i}/assumptions/{j}/id`，避免另造私有错误码。
    """
    owners: dict[str, list[tuple[int, int, str]]] = {}
    for index, task in enumerate(ctx.tasks):
        for position, assumption in enumerate(task.assumptions):
            owners.setdefault(assumption.id, []).append((index, position, task.task_id))

    issues: list[Issue] = []
    for assumption_id, entries in owners.items():
        if len(entries) < 2:
            continue
        first_task = entries[0][2]
        for index, position, task_id in entries[1:]:
            issues.append(
                issue(
                    IssueCode.DUPLICATE_ID,
                    task_path(index, "assumptions", position, "id"),
                    f"假设 ID {assumption_id} 与任务 {first_task} 重复，全计划必须唯一",
                    task_ids=[task_id, first_task],
                    suggestion="重命名该假设并同步引用，或合并重复的假设",
                )
            )
    return issues


def assumption_critical(ctx: RuleContext) -> list[Issue]:
    issues: list[Issue] = []
    for index, task in enumerate(ctx.tasks):
        for position, assumption in enumerate(task.assumptions):
            if assumption.impact is not AssumptionImpact.CRITICAL:
                continue
            issues.append(
                issue(
                    IssueCode.CRITICAL_ASSUMPTION,
                    task_path(index, "assumptions", position),
                    f"关键假设 {assumption.id} 缺少依据：{assumption.text}",
                    task_ids=[task.task_id],
                    suggestion="回到规格补充信息后重新规划；关键假设不得直接推进为正式计划",
                )
            )
    return issues


def requirement_coverage(ctx: RuleContext) -> list[Issue]:
    """must 需求没有任何任务引用即阻断；引用存在也不等于实质覆盖。"""
    referenced = {requirement_id for task in ctx.tasks for requirement_id in task.source_requirement_ids}
    issues: list[Issue] = []
    for index, requirement in enumerate(ctx.requirements):
        if requirement.priority is not RequirementPriority.MUST or requirement.id in referenced:
            continue
        issues.append(
            issue(
                IssueCode.REQUIRED_UNCOVERED,
                pointer("requirements", index),
                f"必需需求 {requirement.id} 没有任何任务引用",
                suggestion="增补任务或在任务的 source_requirement_ids 中引用该需求；结构覆盖仍需人工评审实质交付",
            )
        )
    return issues


def required_categories(ctx: RuleContext) -> list[Issue]:
    if ctx.policy is None or not ctx.policy.required_categories:
        return []
    present = {task.category for task in ctx.tasks}
    missing = [category for category in ctx.policy.required_categories if category not in present]
    if not missing:
        return []
    return [
        issue(
            IssueCode.REQUIRED_CATEGORY,
            pointer("tasks"),
            "缺少规划约束要求的任务类别：" + "、".join(missing),
            suggestion="增补带可验收交付的任务，或调整规划约束",
        )
    ]


def orphan_task(ctx: RuleContext) -> list[Issue]:
    """孤立但有需求引用或过程依据（rationale）的任务合法，缺依据才提示。"""
    issues: list[Issue] = []
    for index, task in enumerate(ctx.tasks):
        if ctx.scan.parents.get(task.task_id) or ctx.scan.children.get(task.task_id):
            continue
        if task.source_requirement_ids or task.rationale.strip():
            continue
        issues.append(
            issue(
                IssueCode.ORPHAN,
                task_path(index),
                f"任务 {task.task_id} 既无依赖关系，也没有需求或过程依据",
                task_ids=[task.task_id],
                suggestion="关联需求 ID、补充规划依据，或删除该任务",
            )
        )
    return issues


def duplicate_task_name(ctx: RuleContext) -> list[Issue]:
    groups: dict[str, list[tuple[int, Task]]] = {}
    for index, task in enumerate(ctx.tasks):
        groups.setdefault(normalize_text(task.name), []).append((index, task))

    issues: list[Issue] = []
    for entries in groups.values():
        if len(entries) < 2:
            continue
        _, first_task = entries[0]
        for index, task in entries[1:]:
            issues.append(
                issue(
                    IssueCode.POSSIBLE_DUPLICATE,
                    task_path(index, "name"),
                    f"任务名称与 {first_task.task_id} 规范化后完全相同：{task.name}",
                    task_ids=[task.task_id, first_task.task_id],
                    suggestion="确认是否重复；语义相近由人工判断，不按相似度自动删除",
                )
            )
    return issues


def duplicate_deliverable(ctx: RuleContext) -> list[Issue]:
    groups: dict[str, list[tuple[int, int, str]]] = {}
    for index, task in enumerate(ctx.tasks):
        for position, deliverable in enumerate(task.deliverables):
            groups.setdefault(normalize_text(deliverable.text), []).append(
                (index, position, task.task_id)
            )

    issues: list[Issue] = []
    for entries in groups.values():
        owners = {task_id for _, _, task_id in entries}
        if len(owners) < 2:
            continue
        _, _, first_task = entries[0]
        for index, position, task_id in entries[1:]:
            issues.append(
                issue(
                    IssueCode.POSSIBLE_DUPLICATE,
                    task_path(index, "deliverables", position, "text"),
                    f"交付内容与 {first_task} 的交付重复",
                    task_ids=[task_id, first_task],
                    suggestion="确认是否为同一交付；重复交付应合并或改写",
                )
            )
    return issues


STRUCTURAL_RULES: tuple[Rule, ...] = (
    Rule("policy-satisfiable", RULES_VERSION, IssueSeverity.ERROR, policy_satisfiable),
    Rule("stage-allowed", RULES_VERSION, IssueSeverity.ERROR, stage_allowed),
    Rule("role-allowed", RULES_VERSION, IssueSeverity.ERROR, role_allowed),
    Rule("category-allowed", RULES_VERSION, IssueSeverity.ERROR, category_allowed),
    Rule("stage-edge-allowed", RULES_VERSION, IssueSeverity.ERROR, stage_edge_allowed),
    Rule("dependency-shape", RULES_VERSION, IssueSeverity.ERROR, dependency_shape),
    Rule("requirement-refs", RULES_VERSION, IssueSeverity.ERROR, requirement_refs),
    Rule("input-dependency", RULES_VERSION, IssueSeverity.ERROR, input_dependency),
    Rule("input-deliverable", RULES_VERSION, IssueSeverity.ERROR, input_deliverable),
    Rule("assumption-unique", RULES_VERSION, IssueSeverity.ERROR, assumption_unique),
    Rule("assumption-critical", RULES_VERSION, IssueSeverity.ERROR, assumption_critical),
)

COVERAGE_RULES: tuple[Rule, ...] = (
    Rule("requirement-coverage", RULES_VERSION, IssueSeverity.ERROR, requirement_coverage),
    Rule("required-categories", RULES_VERSION, IssueSeverity.ERROR, required_categories),
)

ADVISORY_RULES: tuple[Rule, ...] = (
    Rule("orphan-task", RULES_VERSION, IssueSeverity.WARNING, orphan_task),
    Rule("duplicate-task-name", RULES_VERSION, IssueSeverity.WARNING, duplicate_task_name),
    Rule("duplicate-deliverable", RULES_VERSION, IssueSeverity.WARNING, duplicate_deliverable),
)

#: 对外注册表：报告绑定 rules_version，规则本身按 id 可追踪。
RULES: tuple[Rule, ...] = STRUCTURAL_RULES + COVERAGE_RULES + ADVISORY_RULES

__all__ = [
    "ADVISORY_RULES",
    "COVERAGE_RULES",
    "RULES",
    "Rule",
    "RuleContext",
    "STRUCTURAL_RULES",
    "assumption_critical",
    "assumption_unique",
    "category_allowed",
    "dependency_shape",
    "duplicate_deliverable",
    "duplicate_task_name",
    "input_deliverable",
    "input_dependency",
    "orphan_task",
    "policy_satisfiable",
    "requirement_coverage",
    "requirement_refs",
    "required_categories",
    "role_allowed",
    "stage_allowed",
    "stage_edge_allowed",
]

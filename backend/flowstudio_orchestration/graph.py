"""图算法：依赖扫描、Kahn 拓扑分层、迭代三色 DFS 环定位、阶段分组。

这些函数只处理 task_id 与依赖关系，不读数据库、不碰坐标：
- 坐标只影响画布显示，永远不参与顺序计算。
- 批次是"依赖允许的并行机会"，不是资源调度承诺。
- 环定位只报告栈内实际形成的环，Kahn 未处理集合中的环下游任务不算作环节点。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

from flowstudio_contracts import Issue, IssueCode, Task, TaskEdge
from flowstudio_contracts.workflow import ExecutionStage

from .issues import issue, task_path


@dataclass(frozen=True)
class DependencyScan:
    """一次依赖扫描的结果：合法边、缺陷、以及两侧邻接表。"""

    edges: tuple[TaskEdge, ...]
    issues: tuple[Issue, ...]
    children: Mapping[str, tuple[str, ...]]
    parents: Mapping[str, tuple[str, ...]]


def scan_dependencies(tasks: Sequence[Task]) -> DependencyScan:
    """按输入顺序扫描依赖，派生合法边并记录缺失/自环/重复依赖。

    前提：调用方已保证 task_id 唯一（见 `engine.duplicate_task_ids`），
    否则邻接表会按 id 合并，无法定位重复任务。

    只有"存在且非自环"的依赖才进入图：非法边不能污染批次计算，
    但它们仍以 Issue 形式返回，由调用方阻断保存。
    """
    known = {task.task_id for task in tasks}
    issues: list[Issue] = []
    pairs: set[tuple[str, str]] = set()

    for index, task in enumerate(tasks):
        seen: set[str] = set()
        for position, dependency in enumerate(task.dependencies):
            path = task_path(index, "dependencies", position)
            if dependency in seen:
                issues.append(
                    issue(
                        IssueCode.DUPLICATE_DEPENDENCY,
                        path,
                        f"任务 {task.task_id} 重复声明依赖 {dependency}",
                        task_ids=[task.task_id],
                        suggestion="去重后重新编排；不要静默覆盖原输入",
                    )
                )
                continue
            seen.add(dependency)
            if dependency == task.task_id:
                issues.append(
                    issue(
                        IssueCode.SELF_DEPENDENCY,
                        path,
                        f"任务 {task.task_id} 不能依赖自身",
                        task_ids=[task.task_id],
                        edges=[TaskEdge(source=dependency, target=task.task_id)],
                        suggestion="删除该自依赖后重新编排",
                    )
                )
                continue
            if dependency not in known:
                issues.append(
                    issue(
                        IssueCode.MISSING_DEPENDENCY,
                        path,
                        f"任务 {task.task_id} 依赖的上游任务 {dependency} 不存在",
                        task_ids=[task.task_id],
                        edges=[TaskEdge(source=dependency, target=task.task_id)],
                        suggestion="修正为已有任务 ID 或补充该任务，不要静默删边",
                    )
                )
                continue
            pairs.add((dependency, task.task_id))

    children: dict[str, list[str]] = {task.task_id: [] for task in tasks}
    parents: dict[str, list[str]] = {task.task_id: [] for task in tasks}
    for source, target in sorted(pairs):
        children[source].append(target)
        parents[target].append(source)

    return DependencyScan(
        edges=tuple(TaskEdge(source=source, target=target) for source, target in sorted(pairs)),
        issues=tuple(issues),
        children={node: tuple(values) for node, values in children.items()},
        parents={node: tuple(values) for node, values in parents.items()},
    )


def kahn_batches(
    nodes: Sequence[str], children: Mapping[str, Sequence[str]]
) -> tuple[list[list[str]], int]:
    """Kahn 分层：每轮冻结当前 frontier 作为一批，返回批次与已处理节点数。

    处理数小于节点总数说明存在环；调用方再用 `find_cycles` 定位真实环，
    不能把"未处理"直接当成环。
    """
    indegree = {node: 0 for node in nodes}
    for targets in children.values():
        for target in targets:
            indegree[target] += 1

    frontier = sorted(node for node, degree in indegree.items() if degree == 0)
    batches: list[list[str]] = []
    processed = 0
    while frontier:
        batch = list(frontier)  # 本轮集合冻结，避免误把逐个入队顺序当成并行批次
        batches.append(batch)
        processed += len(batch)
        upcoming: list[str] = []
        for node in batch:
            for target in children.get(node, ()):
                indegree[target] -= 1
                if indegree[target] == 0:
                    upcoming.append(target)
        frontier = sorted(upcoming)
    return batches, processed


def find_cycles(
    nodes: Sequence[str], children: Mapping[str, Sequence[str]]
) -> list[list[str]]:
    """迭代式三色 DFS：返回实际环（首尾为同一节点）列表，按发现顺序稳定。"""
    color = {node: 0 for node in nodes}  # 0=未访问 1=栈中 2=已完成
    found: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()

    for root in sorted(nodes):
        if color[root] != 0:
            continue
        color[root] = 1
        path: list[str] = [root]
        position = {root: 0}
        stack: list[tuple[str, Iterator[str]]] = [(root, iter(children.get(root, ())))]
        while stack:
            node, iterator = stack[-1]
            descended = False
            for target in iterator:
                if color[target] == 1:
                    cycle = path[position[target]:] + [target]
                    key = tuple(cycle)
                    if key not in seen:
                        seen.add(key)
                        found.append(cycle)
                elif color[target] == 0:
                    color[target] = 1
                    position[target] = len(path)
                    path.append(target)
                    stack.append((target, iter(children.get(target, ()))))
                    descended = True
                    break
            if not descended:
                stack.pop()
                color[node] = 2
                position.pop(node, None)
                path.pop()
    return found


def group_stages(tasks: Sequence[Task], batches: Sequence[Sequence[str]]) -> list[ExecutionStage]:
    """按任务 stage 分组；阶段顺序取最早拓扑层，再按 stage_id 稳定排序。

    阶段只是活动分类，不隐式产生依赖；同一阶段的任务可跨多个拓扑层。
    """
    batch_of = {task_id: index for index, batch in enumerate(batches) for task_id in batch}
    groups: dict[str, list[tuple[int, str]]] = {}
    for task in tasks:
        if task.task_id not in batch_of:
            continue
        groups.setdefault(task.stage, []).append((batch_of[task.task_id], task.task_id))

    ordered = sorted(groups.items(), key=lambda item: (min(layer for layer, _ in item[1]), item[0]))
    return [
        ExecutionStage(stage_id=stage, task_ids=[task_id for _, task_id in sorted(entries)])
        for stage, entries in ordered
    ]


__all__ = [
    "DependencyScan",
    "find_cycles",
    "group_stages",
    "kahn_batches",
    "scan_dependencies",
]

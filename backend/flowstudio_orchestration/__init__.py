"""FlowStudio 确定性编排器（T05，D 负责）。

设计依据：`tech/docs/system-architecture.md` 第 7、8 节与 `docs/architecture/ORCHESTRATION_ENGINE.md`。
本包只依赖 `tech/flowstudio_contracts`（T01），不依赖 T02 的 FastAPI/仓储，
因此可以独立开发和验收；HTTP 路由、事务与 CAS 由 T02/T07 负责接线。

用法：

    from flowstudio_orchestration import build_plan, validate_workflow

    derivation = build_plan(tasks, spec_content, policy)          # PlanDerivation
    report = validate_workflow(tasks, spec_content, policy)       # ValidationReport

验收：

    cd backend && python -m unittest discover -s tests -v

调用前需让 `flowstudio_contracts` 可导入（`pip install -e tech`，或把仓库的 `tech/`
加入 PYTHONPATH）。测试文件自带路径引导，无需安装。
"""

from __future__ import annotations

from .engine import (
    OrchestrationInputError,
    OrchestrationLimitError,
    build_plan,
    compute_coverage,
    compute_input_hash,
    duplicate_task_ids,
    evaluate,
    validate_workflow,
)
from .graph import (
    DependencyScan,
    find_cycles,
    group_stages,
    kahn_batches,
    scan_dependencies,
)
from .issues import ADVISORY_CODES, issue, normalize_text, pointer, severity_for, task_path
from .rules import (
    ADVISORY_RULES,
    COVERAGE_RULES,
    RULES,
    STRUCTURAL_RULES,
    Rule,
    RuleContext,
)

__all__ = [
    "ADVISORY_CODES",
    "ADVISORY_RULES",
    "COVERAGE_RULES",
    "DependencyScan",
    "OrchestrationInputError",
    "OrchestrationLimitError",
    "RULES",
    "Rule",
    "RuleContext",
    "STRUCTURAL_RULES",
    "build_plan",
    "compute_coverage",
    "compute_input_hash",
    "duplicate_task_ids",
    "evaluate",
    "find_cycles",
    "group_stages",
    "issue",
    "kahn_batches",
    "normalize_text",
    "pointer",
    "scan_dependencies",
    "severity_for",
    "task_path",
    "validate_workflow",
]

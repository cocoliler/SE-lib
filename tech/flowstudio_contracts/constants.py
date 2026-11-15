"""契约版本、规模上限与运行预算的唯一定义。

Schema 中的 min/max 与本文件常量共用同一来源：导出脚本与契约测试会比较两者，
避免"文档一处、模型一处"的漂移。
"""

from __future__ import annotations

from typing import Final

SCHEMA_VERSION: Final[str] = "1.0"
RULES_VERSION: Final[str] = "1.0"
PROMPT_VERSION: Final[str] = "pm-v1"
API_PREFIX: Final[str] = "/api/v1"

# 请求体与规格规模
MAX_BODY_BYTES: Final[int] = 1_048_576
MAX_PRODUCT_NAME: Final[int] = 120
MAX_BACKGROUND: Final[int] = 4000
MAX_GOALS: Final[int] = 20
MAX_TARGET_USERS: Final[int] = 20
MAX_REQUIREMENTS: Final[int] = 200
MAX_REQUIREMENT_CRITERIA: Final[int] = 20
MAX_SPEC_CONSTRAINTS: Final[int] = 30
MAX_SUPPLEMENTAL_TEXT: Final[int] = 12_000
MAX_CONFIRMED_ASSUMPTIONS: Final[int] = 30

# 计划与图规模
MAX_TASKS: Final[int] = 100
MAX_EDGES: Final[int] = 1000
MAX_TASK_DEPENDENCIES: Final[int] = 99
MAX_TASK_DELIVERABLES: Final[int] = 30
MAX_TASK_INPUTS: Final[int] = 200
MAX_TASK_ASSUMPTIONS: Final[int] = 30
MAX_TASK_REQUIREMENT_REFS: Final[int] = 200
MAX_BLOCKING_QUESTIONS: Final[int] = 30
MAX_ISSUE_REFS: Final[int] = 200

# 规划调用预算
MAX_PLANNING_ATTEMPTS: Final[int] = 3
PLANNING_REQUEST_TIMEOUT_SECONDS: Final[int] = 60
PLANNING_DEADLINE_SECONDS: Final[int] = 180
MAX_OUTPUT_TOKENS: Final[int] = 8192
TOKEN_RESERVE_PER_RUN: Final[int] = 40_000
RETRY_BACKOFF_SECONDS: Final[tuple[int, int]] = (1, 3)

# 本进程队列与分页
QUEUE_CAPACITY: Final[int] = 10
PAGE_SIZE_DEFAULT: Final[int] = 20
PAGE_SIZE_MAX: Final[int] = 100

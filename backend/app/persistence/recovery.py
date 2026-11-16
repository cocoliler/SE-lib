"""启动恢复：把未终结的 PlanningRun 标记为 FAILED(PROCESS_INTERRUPTED)。

不自动重发模型请求（避免不可控费用）；重试由用户新建 PlanningRun。
"""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session

from flowstudio_contracts import PlanningStatus
from .repos import dump
from .tables import PlanningRunRow


def mark_interrupted(session: Session) -> int:
    result = session.execute(
        update(PlanningRunRow)
        .where(
            PlanningRunRow.status.in_(
                [PlanningStatus.QUEUED.value, PlanningStatus.RUNNING.value]
            )
        )
        .values(
            status=PlanningStatus.FAILED.value,
            error_json=dump(
                {
                    "code": "PROCESS_INTERRUPTED",
                    "message": "进程在规划完成前退出，本次请求已标记失败；请新建规划请求重试。",
                }
            ),
        )
    )
    return int(result.rowcount or 0)

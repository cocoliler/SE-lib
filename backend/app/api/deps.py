"""API 依赖：会话、分页参数。"""

from __future__ import annotations

from typing import Iterator

from fastapi import Query, Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.sessionmaker()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def page_params(
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
) -> tuple[int, str | None]:
    return limit, cursor

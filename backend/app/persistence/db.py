"""数据库连接与事务封装。

- SQLite PRAGMA：foreign_keys=ON、WAL、busy_timeout=5000、synchronous=NORMAL
- 模型调用绝不在事务内（由应用层保证）
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine_for(database_url: str) -> Engine:
    engine = create_engine(
        database_url,
        future=True,
        connect_args={"check_same_thread": False, "timeout": 5},
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    return engine


def build_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(sessionmaker_: sessionmaker[Session]) -> Iterator[Session]:
    session = sessionmaker_()
    try:
        yield session
    finally:
        session.close()


def integrity_check(engine: Engine) -> str:
    with engine.connect() as connection:
        result = connection.exec_driver_sql("PRAGMA integrity_check").scalar()
    return str(result)

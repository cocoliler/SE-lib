"""建库/迁移：Alembic 或 create_all，并做完整性检查。"""

from __future__ import annotations

import os

from sqlalchemy.engine import Engine

from ..config import ALEMBIC_INI, MIGRATIONS_DIR, Settings
from .db import integrity_check
from .tables import Base


def _run_alembic_upgrade(database_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    # env.py 优先读取该环境变量，避免 URL 中的 % 被 configparser 插值
    os.environ["FLOWSTUDIO_DATABASE_URL"] = database_url
    command.upgrade(config, "head")


def prepare_database(settings: Settings, engine: Engine) -> str:
    """返回 schema_mode：alembic | create_all。"""
    if settings.use_alembic:
        _run_alembic_upgrade(settings.database_url)
        mode = "alembic"
    else:
        Base.metadata.create_all(engine)
        mode = "create_all"
    status = integrity_check(engine)
    if status.lower() != "ok":
        raise RuntimeError(f"数据库完整性检查失败：{status}")
    return mode

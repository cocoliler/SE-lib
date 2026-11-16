"""运行配置：路径、数据库、队列、限额、Host/Origin 白名单。

只从环境变量读取；密钥不落盘、不外发。默认数据目录与 fixtures 均落在 backend/，
避免运行产物污染仓库根目录。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
MIGRATIONS_DIR = BACKEND_ROOT / "migrations"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = _env(name)
    if not raw:
        return default
    items = tuple(part.strip() for part in raw.split(",") if part.strip())
    return items or default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    use_alembic: bool = True
    instance_lock: bool = True
    worker_mode: str = "thread"  # thread | inline
    queue_capacity: int = 10
    max_body_bytes: int = 1024 * 1024
    default_model: str = "deepseek-chat"
    model_allowlist: tuple[str, ...] = ("configured-default", "deepseek-chat")
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver")
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    )
    fixtures_dir: Path | None = None
    frontend_dist: Path | None = None
    log_level: str = "INFO"

    def with_overrides(self, **kwargs) -> "Settings":
        return replace(self, **kwargs)

    @property
    def api_key_present(self) -> bool:
        return bool(_env("DEEPSEEK_API_KEY"))


def load_settings() -> Settings:
    data_dir = Path(_env("FLOWSTUDIO_DATA_DIR") or (BACKEND_ROOT / ".flowstudio"))
    database_url = _env("FLOWSTUDIO_DATABASE_URL") or (
        f"sqlite:///{(data_dir / 'flowstudio.db').as_posix()}"
    )
    fixtures_raw = _env("FLOWSTUDIO_FIXTURES_DIR")
    fixtures_dir = Path(fixtures_raw) if fixtures_raw else (BACKEND_ROOT / "fixtures")
    frontend_raw = _env("FLOWSTUDIO_FRONTEND_DIST")
    frontend_dist = Path(frontend_raw) if frontend_raw else None
    return Settings(
        data_dir=data_dir,
        database_url=database_url,
        use_alembic=_env_bool("FLOWSTUDIO_USE_ALEMBIC", True),
        instance_lock=_env_bool("FLOWSTUDIO_INSTANCE_LOCK", True),
        worker_mode=_env("FLOWSTUDIO_WORKER_MODE", "thread"),
        queue_capacity=_env_int("FLOWSTUDIO_QUEUE_CAPACITY", 10),
        default_model=_env("FLOWSTUDIO_DEFAULT_MODEL", "deepseek-chat"),
        model_allowlist=("configured-default",)
        + _env_list("FLOWSTUDIO_MODEL_ALLOWLIST", ("deepseek-chat",)),
        allowed_hosts=_env_list(
            "FLOWSTUDIO_ALLOWED_HOSTS", ("127.0.0.1", "localhost", "testserver")
        ),
        allowed_origins=_env_list(
            "FLOWSTUDIO_ALLOWED_ORIGINS",
            (
                "http://127.0.0.1:5173",
                "http://localhost:5173",
                "http://127.0.0.1:8000",
                "http://localhost:8000",
            ),
        ),
        fixtures_dir=fixtures_dir,
        frontend_dist=frontend_dist,
        log_level=_env("FLOWSTUDIO_LOG_LEVEL", "INFO"),
    )

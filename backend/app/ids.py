"""ID、时间与游标工具（UTC RFC3339、UUID、不透明游标）。"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def to_iso(value: datetime | None = None) -> str:
    moment = value or utcnow()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def encode_cursor(created_at: str, row_id: str) -> str:
    raw = json.dumps([created_at, row_id], separators=(",", ":"), ensure_ascii=False)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> tuple[str, str]:
    """解析游标；非法游标抛 ValueError（调用方转 422）。"""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        parts = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 - 统一转为可读错误
        raise ValueError("cursor 不合法") from exc
    if not isinstance(parts, list) or len(parts) != 2 or not all(isinstance(p, str) for p in parts):
        raise ValueError("cursor 不合法")
    return parts[0], parts[1]

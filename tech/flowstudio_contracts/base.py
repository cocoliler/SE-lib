"""契约层公共基元：严格模型、受限字符串、ID/时间类型与规范化散列。

本模块是"统一契约"的地基，被任务、规格、规划、工作流与 API DTO 共同复用。
所有字符串先 trim 再校验长度，禁止控制字符（保留 Tab/LF/CR）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Hashable, Iterable
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Final
from uuid import UUID

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, StringConstraints

IDENTIFIER_PATTERN: Final[str] = r"^[A-Za-z][A-Za-z0-9_-]*$"
HASH_PATTERN: Final[str] = r"^[0-9a-f]{64}$"

_ALLOWED_CONTROL: Final[frozenset[str]] = frozenset("\t\n\r")


def _forbidden_control_characters() -> frozenset[str]:
    return frozenset(chr(code) for code in range(0x20) if chr(code) not in _ALLOWED_CONTROL) | {chr(0x7F)}


_FORBIDDEN_CONTROL: Final[frozenset[str]] = _forbidden_control_characters()


def _reject_control_characters(value: str) -> str:
    for character in value:
        if character in _FORBIDDEN_CONTROL:
            raise ValueError(f"禁止使用控制字符 U+{ord(character):04X}")
    return value


def text(min_length: int = 1, max_length: int = 2000, *, identifier: bool = False) -> Any:
    """生成受限字符串类型：strip → 长度 → 标识符模式 → 控制字符。"""
    constraints: dict[str, Any] = {
        "strip_whitespace": True,
        "min_length": min_length,
        "max_length": max_length,
    }
    if identifier:
        constraints["pattern"] = IDENTIFIER_PATTERN
    return Annotated[str, StringConstraints(**constraints), AfterValidator(_reject_control_characters)]


Identifier = text(1, 64, identifier=True)
ShortText = text(1, 120)
BodyText = text(1, 2000)
LongText = text(1, 4000)
RawText = text(0, 12000)
RationaleText = text(0, 2000)
Sha256Hex = Annotated[str, StringConstraints(strip_whitespace=True, pattern=HASH_PATTERN)]


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value.strip())
        except ValueError as exc:  # pragma: no cover - 消息由 pydantic 包装
            raise ValueError("必须为 UUID 字符串") from exc
    raise ValueError("必须为 UUID 字符串")


def _coerce_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        candidate = value.strip()
        if candidate.endswith(("Z", "z")):
            candidate = candidate[:-1] + "+00:00"
        try:
            moment = datetime.fromisoformat(candidate)
        except ValueError as exc:  # pragma: no cover - 消息由 pydantic 包装
            raise ValueError("必须为 RFC3339 时间字符串") from exc
    else:
        raise ValueError("必须为 RFC3339 时间字符串")
    if moment.tzinfo is None:
        raise ValueError("时间必须带时区偏移")
    return moment.astimezone(timezone.utc)


Uuid = Annotated[UUID, BeforeValidator(_coerce_uuid)]
UtcTimestamp = Annotated[datetime, BeforeValidator(_coerce_timestamp)]


def enum_value(enum_type: type[Enum]) -> Any:
    """严格模式下仍接受枚举的字符串取值：HTTP 请求体与 Python 构造行为一致。"""

    def _coerce(value: Any) -> Enum:
        if isinstance(value, enum_type):
            return value
        if isinstance(value, str):
            try:
                return enum_type(value)
            except ValueError as exc:
                allowed = ", ".join(repr(item.value) for item in enum_type)
                raise ValueError(f"必须为 {enum_type.__name__} 取值之一：{allowed}") from exc
        raise ValueError(f"必须为 {enum_type.__name__} 的字符串取值")

    return Annotated[enum_type, BeforeValidator(_coerce)]


class StrictModel(BaseModel):
    """拒绝未知字段、拒绝类型强转的基类；写接口与模型输出共用。"""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)

    def to_json(self) -> str:
        return canonical_json(self.model_dump(mode="json", by_alias=True))


def duplicates(values: Iterable[Hashable]) -> set[Hashable]:
    """返回出现多次的值；用于各处"局部唯一性"校验，避免每处各写一遍。"""
    seen: set[Hashable] = set()
    repeated: set[Hashable] = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return repeated


def canonical_json(payload: Any) -> str:
    """按键排序、无多余空格的 UTF-8 规范化 JSON；用于散列与导出比对。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_hex(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def content_hash(model: StrictModel) -> str:
    """业务对象散列：排除运行信息，对规范化 JSON 取值。"""
    return sha256_hex(model.model_dump(mode="json", by_alias=True))

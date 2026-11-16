"""幂等命令：scope = HTTP 方法 + 资源路径；同键同摘要返回原结果，同键异内容 409。

校验失败发生在进入处理函数之前（FastAPI 的 422），不占用键。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from flowstudio_contracts import sha256_hex

from ..errors import idempotency_conflict, validation_failed
from ..persistence import repos


@dataclass
class IdempotencyContext:
    scope: str
    key: str | None
    body_hash: str

    @property
    def enabled(self) -> bool:
        return self.key is not None


def read(request: Request, body: BaseModel) -> IdempotencyContext:
    scope = f"{request.method} {request.url.path}"
    key = request.headers.get("Idempotency-Key")
    body_hash = sha256_hex(body.model_dump(mode="json", by_alias=True))
    if key is not None:
        try:
            uuid.UUID(key)
        except ValueError as exc:
            raise validation_failed("Idempotency-Key 必须是 UUID 字符串") from exc
    return IdempotencyContext(scope=scope, key=key, body_hash=body_hash)


def replay(session: Session, context: IdempotencyContext) -> JSONResponse | None:
    if not context.enabled:
        return None
    row = repos.get_command(session, context.scope, context.key or "")
    if row is None:
        return None
    if row.request_hash != context.body_hash:
        raise idempotency_conflict()
    payload = json.loads(row.result_json)
    return JSONResponse(status_code=payload["status"], content=payload["body"])


def store(
    session: Session, context: IdempotencyContext, status_code: int, body: dict
) -> None:
    if not context.enabled:
        return
    repos.put_command(
        session,
        context.scope,
        context.key or "",
        context.body_hash,
        status_code,
        body,
    )

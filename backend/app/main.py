"""FastAPI 应用入口：生命周期、守卫中间件、错误信封。

启动顺序：数据目录 → 实例锁 → 引擎/会话 → 迁移 → 恢复未终结规划 → 启动队列。

契约边界：所有请求/响应模型来自 `flowstudio_contracts`；编排算法来自
`flowstudio_orchestration`；本层只做生命周期、存储与错误映射。
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from flowstudio_contracts import SCHEMA_VERSION
from flowstudio_contracts.constants import MAX_BODY_BYTES
from flowstudio_orchestration import OrchestrationInputError

from .api import api_router
from .application.planning import PlanningCoordinator
from .application.queue import PlanningQueue
from .config import Settings, load_settings
from .errors import (
    ApiError,
    error_body,
    forbidden_host_or_origin,
    payload_too_large,
    storage_busy,
    validation_failed,
)
from .ids import new_id
from .persistence import (
    InstanceLock,
    build_sessionmaker,
    create_engine_for,
    mark_interrupted,
    prepare_database,
)
from .providers.base import PlanningEngine
from .providers.default import DefaultPlanningEngine

LOGGER = logging.getLogger(__name__)


class GuardMiddleware:
    """请求 ID、Host/Origin 校验、1 MiB 请求体上限。"""

    def __init__(self, app, settings: Settings) -> None:  # noqa: ANN001
        self.app = app
        self.settings = settings
        self.max_bytes = min(settings.max_body_bytes, MAX_BODY_BYTES)

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        request_id = headers.get("x-request-id") or new_id()
        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        host = headers.get("host", "").split(":")[0].lower()
        if host and host not in self.settings.allowed_hosts:
            await self._reject(
                send,
                403,
                error_body(
                    "ORIGIN_FORBIDDEN", f"Host {host} 不被允许", [], request_id
                ),
            )
            return
        origin = headers.get("origin")
        if origin and origin not in self.settings.allowed_origins:
            await self._reject(
                send,
                403,
                error_body(
                    "ORIGIN_FORBIDDEN", f"Origin {origin} 不被允许", [], request_id
                ),
            )
            return

        replay = receive
        if scope["method"] in {"POST", "PUT", "PATCH"}:
            chunks: list[bytes] = []
            total = 0
            more = True
            while more:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                total += len(chunk)
                if total > self.max_bytes:
                    await self._reject(
                        send,
                        413,
                        error_body(
                            "PAYLOAD_TOO_LARGE",
                            f"请求体超过 {self.max_bytes} 字节上限",
                            [],
                            request_id,
                        ),
                    )
                    return
                chunks.append(chunk)
                more = message.get("more_body", False)
            buffered = b"".join(chunks)
            delivered = False

            async def replay(request_message=None):  # noqa: ANN001, ANN202
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": buffered, "more_body": False}
                return {"type": "http.disconnect"}

        async def send_with_id(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append(
                    (b"x-request-id", request_id.encode("latin-1"))
                )
            await send(message)

        await self.app(scope, replay, send_with_id)

    async def _reject(self, send, status: int, body: dict[str, Any]) -> None:  # noqa: ANN001
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_id = body["error"]["request_id"]
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(raw)).encode()),
                    (b"x-request-id", request_id.encode("latin-1")),
                    (b"access-control-allow-origin", b"*"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": raw})


def create_app(settings: Settings | None = None, engine: PlanningEngine | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ANN201
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        lock = InstanceLock(settings.data_dir / "instance.lock") if settings.instance_lock else None
        if lock is not None:
            lock.acquire()

        db_engine = create_engine_for(settings.database_url)
        app.state.settings = settings
        app.state.db_engine = db_engine
        app.state.sessionmaker = build_sessionmaker(db_engine)
        app.state.schema_mode = prepare_database(settings, db_engine)

        with app.state.sessionmaker() as session:
            interrupted = mark_interrupted(session)
            session.commit()
        if interrupted:
            LOGGER.warning("启动恢复：%s 个未终结规划请求已标记 FAILED", interrupted)

        adapter = engine or DefaultPlanningEngine(settings.fixtures_dir)
        app.state.engine = adapter
        coordinator = PlanningCoordinator(app.state.sessionmaker, adapter)
        planning_queue = PlanningQueue(
            settings.queue_capacity, coordinator.process, settings.worker_mode
        )
        app.state.coordinator = coordinator
        app.state.queue = planning_queue
        planning_queue.start()

        try:
            yield
        finally:
            planning_queue.stop()
            db_engine.dispose()
            if lock is not None:
                lock.release()

    app = FastAPI(
        title="FlowStudio API",
        version=SCHEMA_VERSION,
        description="规划闭环后端：Design Spec → PM Agent → 任务分解 → 编排 → 计划版本",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )
    app.add_middleware(GuardMiddleware, settings=settings)

    app.include_router(api_router)

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.issues, request_id),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        details = "；".join(
            f"{'/'.join(str(part) for part in error.get('loc', ()))}: {error.get('msg', '')}"
            for error in exc.errors()
        )
        error = validation_failed(f"请求未通过契约校验：{details}")
        return JSONResponse(
            status_code=422,
            content=error_body(error.code, error.message, [], request_id),
        )

    @app.exception_handler(OrchestrationInputError)
    async def orchestration_handler(
        request: Request, exc: OrchestrationInputError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        error = validation_failed(f"编排输入超出契约上限：{exc}")
        return JSONResponse(
            status_code=422,
            content=error_body(error.code, error.message, [], request_id),
        )

    @app.exception_handler(OperationalError)
    async def storage_handler(request: Request, exc: OperationalError) -> JSONResponse:
        text = str(exc).lower()
        request_id = getattr(request.state, "request_id", "unknown")
        if "locked" in text or "busy" in text:
            error = storage_busy()
            return JSONResponse(
                status_code=error.status_code,
                content=error_body(error.code, error.message, [], request_id),
            )
        return JSONResponse(
            status_code=500,
            content=error_body("INTERNAL_ERROR", "本地存储错误", [], request_id),
        )

    if settings.frontend_dist is not None and settings.frontend_dist.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(settings.frontend_dist), html=True), name="ui")

    return app


app = create_app()

__all__ = ["app", "create_app", "forbidden_host_or_origin", "payload_too_large"]

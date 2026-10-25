"""FastAPI 应用工厂：装配模块路由、统一信封、后台循环。

路由挂载约定：REST 路由统一 /v1 前缀；WSS 路由（/v1/realtime、/v1/connectors/realtime）
自带完整路径（不受前缀影响）。
"""

import asyncio
import contextlib
import logging

from fastapi import FastAPI

from aichat.core.config import Settings, get_settings
from aichat.core.context import AppContext
from aichat.core.db import Database
from aichat.core.envelope import EnvelopeMiddleware, register_exception_handlers
from aichat.core.security import CredentialCipher
from aichat.modules.realtime.hub import RealtimeHub
from aichat.worker import loops as worker_loops

logger = logging.getLogger("aichat")

# 确保所有模块的表都已注册到 Base.metadata
from aichat.modules import (  # noqa: F401,E402
    agents,
    audit,
    contacts,
    conversations,
    identity,
    messages,
    pairing,
    realtime,
    runs,
)
from aichat.modules.agents.router import router as agents_router  # noqa: E402
from aichat.modules.contacts.router import router as contacts_router  # noqa: E402
from aichat.modules.conversations.router import router as conversations_router  # noqa: E402
from aichat.modules.identity.router import router as identity_router  # noqa: E402
from aichat.modules.messages.router import router as messages_router  # noqa: E402
from aichat.modules.pairing.router import router as pairing_router  # noqa: E402
from aichat.modules.realtime import connector_gateway, human_ws  # noqa: E402
from aichat.modules.realtime.router import router as realtime_router  # noqa: E402
from aichat.modules.runs.router import router as runs_router  # noqa: E402


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings)
    ctx = AppContext(settings=settings, db=db, hub=RealtimeHub(), cipher=CredentialCipher(settings))

    app = FastAPI(title="AIChat API", version="1.0.0", docs_url="/docs", openapi_url="/openapi.json")
    app.state.ctx = ctx
    register_exception_handlers(app)
    app.add_middleware(EnvelopeMiddleware)

    for router in (identity_router, contacts_router, conversations_router, messages_router,
                   agents_router, pairing_router, realtime_router, runs_router):
        app.include_router(router, prefix="/v1")
    # WSS 路由自带完整路径，不加重叠前缀
    app.include_router(human_ws.router)
    app.include_router(connector_gateway.router)

    @app.on_event("startup")
    async def on_startup() -> None:
        if not settings.is_prod:
            await db.create_all()
        app.state.loop_tasks = [asyncio.create_task(loop(ctx)) for loop in worker_loops.ALL_LOOPS]

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        for task in getattr(app.state, "loop_tasks", []):
            task.cancel()
        for task in getattr(app.state, "loop_tasks", []):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await db.dispose()

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"ok": True}

    return app


app = create_app()

"""人类事件 WSS：/v1/realtime。票据首帧认证 → welcome → 事件推送（拉模式 drain）。"""

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from aichat.core.context import AppContext
from aichat.core.errors import ApiError
from aichat.modules.identity.service import IdentityService
from aichat.modules.realtime.hub import HumanConnection
from aichat.modules.realtime.service import RealtimeService

logger = logging.getLogger("aichat.realtime")

router = APIRouter()


@router.websocket("/v1/realtime")
async def realtime_ws(websocket: WebSocket) -> None:
    ctx: AppContext = websocket.app.state.ctx
    await websocket.accept()
    # 1) 限时首帧票据
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=ctx.settings.ws_first_frame_seconds)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
        await websocket.close(code=4401)
        return
    if not isinstance(first, dict) or first.get("type") != "ticket" or not first.get("ticket"):
        await websocket.close(code=4401)
        return
    async with ctx.db.session_factory() as session:
        try:
            account_id = await IdentityService(ctx, session).consume_ws_ticket(first["ticket"], "human_events")
        except ApiError:
            await websocket.close(code=4401)
            return
    from aichat.modules.realtime.models import EventStream

    async with ctx.db.session_factory() as session:
        stream_row = await session.get(EventStream, account_id)
        last_cursor = stream_row.last_cursor if stream_row is not None else 0

    conn = HumanConnection(account_id=account_id, drain=lambda: None)
    sent_lock = asyncio.Lock()

    async def drain() -> None:
        nonlocal last_cursor
        async with sent_lock:
            async with ctx.db.session_factory() as session:
                service = RealtimeService(ctx, session)
                while True:
                    page = await service.events_page(account_id, after=last_cursor, limit=100)
                    for frame in page["items"]:
                        await websocket.send_json(frame)
                    last_cursor = max(last_cursor, int(page["next_cursor"]))
                    if not page["has_more"] or not page["items"]:
                        break

    conn._drain = drain
    await ctx.hub.add_human(conn)

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(ctx.settings.heartbeat_seconds)
            with contextlib.suppress(Exception):
                await websocket.send_json({"type": "heartbeat"})

    hb_task = asyncio.create_task(heartbeat())
    try:
        await websocket.send_json({
            "type": "welcome",
            "current_cursor": str(last_cursor),
            "heartbeat_seconds": ctx.settings.heartbeat_seconds,
        })
        await drain()
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        logger.exception("realtime ws 异常 account=%s", account_id)
    finally:
        hb_task.cancel()
        await ctx.hub.remove_human(conn)
        with contextlib.suppress(Exception):
            await websocket.close()

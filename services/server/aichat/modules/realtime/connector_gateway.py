"""连接器网关：/v1/connectors/realtime。票据认证 → hello/welcome → run.* 控制帧。

每帧独立短事务处理；执行身份（execution_id/attempt/fencing）逐帧验证。
心跳同时续租该连接器名下 running 尝试（租约=执行所有权）。
"""

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from aichat.core.context import AppContext
from aichat.core.errors import ApiError
from aichat.core.security import utcnow
from aichat.modules.identity.service import IdentityService
from aichat.modules.pairing.models import Connector
from aichat.modules.realtime.hub import ConnectorConnection
from aichat.modules.runs.models import Run, RunAttempt
from aichat.modules.runs.service import RunsService

logger = logging.getLogger("aichat.gateway")

router = APIRouter()


async def _error_frame(websocket: WebSocket, code: str, message: str, request_id: str | None = None) -> None:
    frame = {"type": "error", "code": code, "message": message}
    if request_id:
        frame["request_id"] = request_id
    with contextlib.suppress(Exception):
        await websocket.send_json(frame)


@router.websocket("/v1/connectors/realtime")
async def connector_ws(websocket: WebSocket) -> None:
    ctx: AppContext = websocket.app.state.ctx
    await websocket.accept()
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
            connector_id = await IdentityService(ctx, session).consume_ws_ticket(first["ticket"], "connector")
        except ApiError:
            await websocket.close(code=4401)
            return
        connector = await session.get(Connector, connector_id)
        if connector is None or connector.revoked_at is not None:
            await websocket.close(code=4401)
            return
        connector.status = "online"
        connector.last_seen_at = utcnow()

    send_lock = asyncio.Lock()

    async def _send(frame: dict) -> None:
        async with send_lock:
            await websocket.send_json(frame)

    conn = ConnectorConnection(connector_id=connector_id, agent_account_id=connector.agent_account_id,
                               send=_send)
    old = await ctx.hub.add_connector(conn)
    if old is not None:
        # 旧连接因代次更替立即失效
        pass
    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                continue
            mtype = message.get("type")
            request_id = message.get("request_id")
            if mtype in ("heartbeat", "connector.hello", "connector.ready", "connector.degraded"):
                async with ctx.db.session_factory() as session:
                    await _handle_lifecycle(ctx, session, connector_id, message)
                    await session.commit()
                if mtype == "connector.hello":
                    await _send({
                        "type": "connector.welcome",
                        "protocol_version": 1,
                        "heartbeat_seconds": ctx.settings.heartbeat_seconds,
                        "lease_seconds": ctx.settings.run_lease_seconds,
                        "effective_capabilities": ["chat.text", "output.stream", "run.cancel", "run.query"],
                        "request_id": request_id,
                    })
                continue
            if mtype == "run.query":
                async with ctx.db.session_factory() as session:
                    runs = RunsService(ctx, session)
                    attempt = await runs.get_attempt_by_execution(message.get("execution_id", ""))
                    if attempt is None:
                        await _error_frame(websocket, "NOT_FOUND", "执行不存在", request_id)
                    else:
                        run = await session.get(Run, attempt.run_id)
                        await _send({
                            "type": "run.status",
                            "execution_id": attempt.execution_id,
                            "run_id": attempt.run_id,
                            "state": run.state if run is not None else "unknown",
                            "attempt_no": attempt.attempt_no,
                            "fencing_token": attempt.fencing_token,
                            "may_continue": attempt.state == "running",
                            "request_id": request_id,
                        })
                    await session.commit()
                continue
            # run.* 执行帧
            try:
                async with ctx.db.session_factory() as session:
                    runs = RunsService(ctx, session)
                    await _handle_run_frame(ctx, session, runs, connector_id, message)
                    await session.commit()
            except ApiError as exc:
                await _error_frame(websocket, exc.code, exc.message, request_id)
            except Exception:
                logger.exception("连接器帧处理异常 type=%s", mtype)
                await _error_frame(websocket, "TEMPORARILY_UNAVAILABLE", "服务暂时不可用", request_id)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await ctx.hub.remove_connector(conn)
        with contextlib.suppress(Exception):
            async with ctx.db.session_factory() as session:
                connector_row = await session.get(Connector, connector_id)
                if connector_row is not None and connector_row.status == "online":
                    connector_row.status = "offline"
                await session.commit()
            await websocket.close()


async def _handle_lifecycle(ctx: AppContext, session, connector_id: str, message: dict) -> None:
    connector = await session.get(Connector, connector_id)
    if connector is None:
        return
    connector.last_seen_at = utcnow()
    mtype = message.get("type")
    if mtype == "connector.ready":
        connector.status = "ready"
    elif mtype == "connector.degraded":
        connector.status = "degraded"
    elif mtype == "heartbeat":
        # 心跳顺带续租该连接器名下的 running 尝试（执行所有权续约）
        rows = list(await session.scalars(
            select(RunAttempt).where(RunAttempt.connector_id == connector_id,
                                     RunAttempt.state == "running")
        ))
        from datetime import timedelta

        for attempt in rows:
            attempt.lease_until = utcnow() + timedelta(seconds=ctx.settings.run_lease_seconds)


async def _handle_run_frame(ctx: AppContext, session, runs: RunsService, connector_id: str, message: dict) -> None:
    mtype = message.get("type")
    common = (
        message.get("run_id", ""),
        message.get("execution_id", ""),
        int(message.get("attempt_no", 0)),
        int(message.get("fencing_token", 0)),
    )
    if mtype == "run.accepted":
        await runs.ack(*common)
    elif mtype == "run.started":
        await runs.start(*common)
    elif mtype == "run.delta":
        import hashlib

        await runs.apply_delta(
            *common,
            chunk_index=int(message.get("chunk_index", -1)),
            text=str(message.get("text", "")),
            chunk_hash=message.get("chunk_hash") or hashlib.sha256(
                str(message.get("text", "")).encode()).hexdigest(),
        )
    elif mtype == "run.completed":
        await runs.complete(
            *common,
            final_text=message.get("final_text"),
            content_hash=message.get("content_hash"),
            last_chunk_index=int(message.get("last_chunk_index", -1)),
            usage=message.get("usage"),
            finish_reason=message.get("finish_reason"),
        )
    elif mtype == "run.failed":
        await runs.fail(
            *common,
            error_code=str(message.get("error_code", "connector_error")),
            message=str(message.get("message", ""))[:512],
            side_effect=message.get("side_effect_status", "none"),
        )
    elif mtype == "run.cancelled":
        await runs.confirm_cancelled(
            message.get("execution_id", ""),
            message.get("side_effect_status", "none"),
        )
    else:
        from aichat.core.errors import validation_failed

        raise validation_failed(f"未知运行命令: {mtype}")

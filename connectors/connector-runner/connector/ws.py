"""连接器 WSS 会话客户端（契约 contracts/PROTOCOL.md §7 连接器 WSS）。

会话建立：访问令牌 → POST /v1/realtime-tickets(audience=connector) → 连接
{base}/v1/connectors/realtime → 首帧 {"type":"ticket"} → connector.hello →
等 connector.welcome → connector.ready。

主循环：按 heartbeat_seconds 心跳；run.offer 先查本地账本去重（已存在则 run.query 附着）；
执行链 run.accepted → run.started → run.delta(chunk_index 从 0) → run.completed
（短文本 final_text，长文本 chunks 拼接的 SHA-256 content_hash）；run.cancel 尽力停止后
run.cancelled。断线指数退避（1/2/4…最大 30 秒）重连，重连后对账本未终态执行逐个 run.query。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
import websockets
from websockets.asyncio.client import connect as ws_connect

from .adapters.base import AgentAdapter
from .client import ApiError, post_json
from .config import ServerConfig
from .ledger import Ledger, TERMINAL_STATUSES
from .tokens import SessionRevokedError, TokenManager

log = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
DEFAULT_HEARTBEAT_SECONDS = 20
WELCOME_TIMEOUT_SECONDS = 15
FINAL_TEXT_MAX_BYTES = 32 * 1024  # final_text ≤ 32KiB；超出改用 content_hash
RECONNECT_BACKOFF_MAX_SECONDS = 30.0
CONNECT_CAPABILITIES = ["chat.text", "output.stream", "run.cancel", "run.query"]
# 这些错误码表示服务端已拒绝本执行的提交，应停止继续发送
STALE_ERROR_CODES = {"STALE_FENCE", "IDEMPOTENCY_CONFLICT"}


def realtime_ws_url(server_base_url: str) -> str:
    """https://host → wss://host/v1/connectors/realtime。"""
    url = httpx.URL(server_base_url)
    scheme = "wss" if url.scheme == "https" else "ws"
    return str(url.copy_with(scheme=scheme)).rstrip("/") + "/v1/connectors/realtime"


def _parse_rfc3339(value: object) -> float | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _to_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


@dataclass
class ActiveRun:
    """一个在途执行（含 asyncio 任务与控制标志）。"""

    execution_id: str
    run_id: str
    attempt_no: Any = None
    fencing_token: Any = None
    context: list[dict] = field(default_factory=list)
    system_prompt: str | None = None
    policy: dict = field(default_factory=dict)
    chunks: list[str] = field(default_factory=list)
    task: asyncio.Task | None = None
    cancel_requested: bool = False
    stale: bool = False


class ConnectorSession:
    """管理一次长生命周期连接器会话（内部自动重连）。"""

    def __init__(
        self,
        *,
        config: ServerConfig,
        token_manager: TokenManager,
        ledger: Ledger,
        adapter: AgentAdapter,
        http: httpx.AsyncClient,
        adapter_kind: str,
        connector_id: str,
        adapter_version: str = "0.1.0",
    ) -> None:
        self._config = config
        self._tokens = token_manager
        self._ledger = ledger
        self.adapter = adapter
        self._http = http
        self._adapter_kind = adapter_kind
        self._connector_id = connector_id
        self._adapter_version = adapter_version
        self._ws: Any = None
        self._active: dict[str, ActiveRun] = {}

    # ------------------------------------------------------------------ 生命周期

    async def run_forever(self) -> None:
        """循环连接；断线按 1/2/4…（最大 30 秒）退避重连。凭据撤销时抛出。"""
        backoff = 1.0
        while True:
            welcomed = False
            try:
                welcomed = await self._session_once()
            except SessionRevokedError:
                raise
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # WSS 握手 401：丢弃令牌缓存，下轮强制刷新
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code == 401:
                    self._tokens.invalidate()
                log.warning("会话中断：%s", exc)
            if welcomed:
                backoff = 1.0  # 成功握手过则重置退避
            log.info("将在 %.0f 秒后重连", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_BACKOFF_MAX_SECONDS)

    async def _session_once(self) -> bool:
        """建立一次完整会话；成功完成 welcome 握手返回 True。"""
        access_token = await self._tokens.get_access_token()
        ticket = await self._fetch_ticket(access_token)
        url = realtime_ws_url(self._config.server_base_url)
        log.info("连接 %s", url)
        async with ws_connect(url, open_timeout=15, ping_interval=None, max_size=16 * 1024 * 1024) as ws:
            self._ws = ws
            # 1. 首帧提交一次性票据
            await self._send({"type": "ticket", "ticket": ticket["ticket"]})
            # 2. hello
            await self._send(
                {
                    "type": "connector.hello",
                    "protocol_version": PROTOCOL_VERSION,
                    "connector_id": self._connector_id,
                    "adapter_kind": self._adapter_kind,
                    "adapter_version": self._adapter_version,
                    "capabilities": CONNECT_CAPABILITIES,
                }
            )
            # 3. 等待 welcome
            welcome = await self._wait_welcome()
            heartbeat = _to_int(welcome.get("heartbeat_seconds")) or DEFAULT_HEARTBEAT_SECONDS
            log.info(
                "已连接（heartbeat=%ss lease=%ss effective_capabilities=%s）",
                heartbeat,
                welcome.get("lease_seconds"),
                welcome.get("effective_capabilities"),
            )
            # 4. 上报就绪
            await self._send({"type": "connector.ready"})
            # 5. 恢复：对账本中未终态执行逐个 run.query
            await self._resume_unfinished()
            try:
                await self._main_loop(heartbeat)
            finally:
                self._ws = None
                await self._abort_active()
        return True

    # ------------------------------------------------------------------ 帧收发

    async def _send(self, frame: dict) -> None:
        if self._ws is None:
            raise ConnectionError("WebSocket 未连接")
        await self._ws.send(json.dumps(frame, ensure_ascii=False))

    async def _fetch_ticket(self, access_token: str) -> dict:
        try:
            return await post_json(
                self._http,
                f"{self._config.server_base_url}/v1/realtime-tickets",
                json_body={"audience": "connector"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except ApiError as err:
            if err.code in {"SESSION_REVOKED", "AUTH_INVALID"}:
                self._tokens.invalidate()
                raise SessionRevokedError(
                    f"获取 WSS 票据失败（{err.code}）：连接器凭据已失效，需重新配对。"
                ) from err
            raise

    async def _wait_welcome(self) -> dict:
        deadline = time.monotonic() + WELCOME_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=deadline - time.monotonic())
            except TimeoutError:
                break
            frame = json.loads(raw)
            if frame.get("type") == "connector.welcome":
                return frame
            log.debug("welcome 前忽略帧 %s", frame.get("type"))
        raise ConnectionError("未在超时前收到 connector.welcome")

    async def _main_loop(self, heartbeat_seconds: int) -> None:
        next_beat = time.monotonic() + heartbeat_seconds
        while True:
            timeout = next_beat - time.monotonic()
            if timeout <= 0:
                await self._send({"type": "heartbeat"})
                next_beat = time.monotonic() + heartbeat_seconds
                continue
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            except TimeoutError:
                continue  # 回到循环顶发送心跳
            await self._handle_frame(json.loads(raw))

    async def _handle_frame(self, frame: dict) -> None:
        ftype = frame.get("type")
        if ftype in {"heartbeat", "pong"}:
            return
        if ftype == "run.offer":
            await self._handle_offer(frame)
        elif ftype == "run.cancel":
            await self._handle_cancel(frame)
        elif ftype == "run.status":
            await self._handle_status(frame)
        elif ftype == "error":
            await self._handle_error_frame(frame)
        else:
            log.debug("忽略帧 %s", ftype)

    # ------------------------------------------------------------------ run 控制

    async def _handle_offer(self, frame: dict) -> None:
        execution_id = frame.get("execution_id")
        run_id = frame.get("run_id")
        if not execution_id or not run_id:
            log.error("run.offer 缺少 execution_id/run_id，已忽略：%r", frame)
            return

        existing = self._ledger.get(execution_id)
        if existing is not None:
            # 幂等重放：不新建、不重复执行，直接 run.query 附着原执行
            log.info(
                "run.offer 重放（execution_id=%s 账本状态 %s），发送 run.query 附着",
                execution_id,
                existing.status,
            )
            await self._send({"type": "run.query", "run_id": run_id, "execution_id": execution_id})
            return

        attempt_no = frame.get("attempt_no")
        fencing_token = frame.get("fencing_token")
        context = list(frame.get("context") or [])
        system_prompt = frame.get("system_prompt")
        policy = dict(frame.get("policy") or {})

        self._ledger.upsert(
            execution_id,
            run_id=run_id,
            status="accepted",
            attempt_no=attempt_no,
            fencing_token=fencing_token,
        )
        await self._send(
            {
                "type": "run.accepted",
                "run_id": run_id,
                "execution_id": execution_id,
                "attempt_no": attempt_no,
                "fencing_token": fencing_token,
            }
        )
        run = ActiveRun(
            execution_id=execution_id,
            run_id=run_id,
            attempt_no=attempt_no,
            fencing_token=fencing_token,
            context=context,
            system_prompt=system_prompt,
            policy=policy,
        )
        run.task = asyncio.create_task(self._execute_run(run))
        self._active[execution_id] = run

    async def _execute_run(self, run: ActiveRun) -> None:
        common = {
            "run_id": run.run_id,
            "execution_id": run.execution_id,
            "attempt_no": run.attempt_no,
            "fencing_token": run.fencing_token,
        }
        try:
            await self._send({"type": "run.started", **common})
            self._ledger.upsert(run.execution_id, status="running")

            max_output_bytes = _to_int(run.policy.get("max_output_bytes"))
            deadline_ts = _parse_rfc3339(run.policy.get("deadline_at"))
            total_bytes = 0
            truncated = False

            async for piece in self.adapter.run(run.context, run.system_prompt):
                if run.stale or run.cancel_requested:
                    break
                piece_bytes = len(piece.encode("utf-8"))
                if max_output_bytes is not None and total_bytes + piece_bytes > max_output_bytes:
                    self._ledger.upsert(run.execution_id, status="failed", chunks=run.chunks)
                    await self._send({"type": "run.failed", **common, "error_code": "OUTPUT_LIMIT",
                                      "message": "输出超过允许的字节上限", "side_effect_status": "none"})
                    return
                run.chunks.append(piece)
                self._ledger.upsert(run.execution_id, chunks=run.chunks)
                total_bytes += piece_bytes
                await self._send(
                    {
                        "type": "run.delta",
                        **common,
                        "chunk_index": len(run.chunks) - 1,
                        "text": piece,
                    }
                )
                if max_output_bytes is not None and total_bytes >= max_output_bytes:
                    truncated = True
                    break
                if deadline_ts is not None and time.time() >= deadline_ts:
                    break

            if run.cancel_requested:
                self._ledger.upsert(run.execution_id, status="cancelled", chunks=run.chunks)
                await self._send({"type": "run.cancelled", **common, "side_effect_status": "none"})
                return
            if run.stale:
                # 服务端已判 stale/冲突，账本在错误帧处理中置 failed；不再提交
                return
            if deadline_ts is not None and time.time() >= deadline_ts:
                self._ledger.upsert(run.execution_id, status="failed", chunks=run.chunks)
                await self._send(
                    {
                        "type": "run.failed",
                        **common,
                        "error_code": "DEADLINE_EXCEEDED",
                        "message": "输出超出 deadline_at",
                        "side_effect_status": "unknown",
                    }
                )
                return

            final_text = "".join(run.chunks)
            self._ledger.upsert(
                run.execution_id, status="completion_pending", chunks=run.chunks, final_text=final_text
            )
            completed: dict[str, Any] = {
                "type": "run.completed",
                **common,
                "last_chunk_index": len(run.chunks) - 1,
                "finish_reason": "length" if truncated else "stop",
            }
            if len(final_text.encode("utf-8")) <= FINAL_TEXT_MAX_BYTES:
                completed["final_text"] = final_text
            else:
                # 长文本：用已发 chunks 拼接文本的 SHA-256 作为 content_hash
                completed["content_hash"] = hashlib.sha256(
                    final_text.encode("utf-8")
                ).hexdigest()
            await self._send(completed)
            await self._send({"type": "run.query", "run_id": run.run_id, "execution_id": run.execution_id})
        except asyncio.CancelledError:
            raise
        except (ConnectionError, OSError, websockets.exceptions.ConnectionClosed):
            # Keep the durable checkpoint/pending completion for reconnect.
            log.info("执行 %s 传输中断，等待重连对账", run.execution_id)
        except Exception:
            log.exception("执行 %s 失败", run.execution_id)
            self._ledger.upsert(run.execution_id, status="failed")
            try:
                await self._send(
                    {
                        "type": "run.failed",
                        **common,
                        "error_code": "ADAPTER_ERROR",
                        # Upstream response bodies and adapter exceptions may
                        # contain private data; only local logs receive details.
                        "message": "适配器执行失败，请检查连接器本机日志",
                        "side_effect_status": "unknown",
                    }
                )
            except Exception:
                log.debug("上报 run.failed 失败", exc_info=True)
        finally:
            self._active.pop(run.execution_id, None)

    async def _handle_cancel(self, frame: dict) -> None:
        execution_id = frame.get("execution_id")
        log.info("收到 run.cancel（execution_id=%s reason=%s）", execution_id, frame.get("reason"))
        run = self._active.get(str(execution_id))
        if run is not None:
            run.cancel_requested = True
            try:
                self.adapter.cancel()  # 尽力停止适配器；run.cancelled 由执行任务发送
            except Exception:
                log.debug("适配器 cancel 抛错", exc_info=True)
            return
        record = self._ledger.get(str(execution_id)) if execution_id else None
        if record is not None and not record.is_terminal:
            self._ledger.upsert(record.execution_id, status="cancelled")
            await self._send(
                {
                    "type": "run.cancelled",
                    "run_id": frame.get("run_id") or record.run_id,
                    "execution_id": record.execution_id,
                    "attempt_no": record.attempt_no,
                    "fencing_token": record.fencing_token,
                    "side_effect_status": "none",
                }
            )

    async def _handle_status(self, frame: dict) -> None:
        """run.status（run.query 的应答或服务端主动通知）。"""
        execution_id = frame.get("execution_id")
        state = frame.get("state")
        if not execution_id:
            return
        record = self._ledger.get(str(execution_id))
        if record is None:
            log.warning("run.status 对应未知执行 %s（state=%s）", execution_id, state)
            return
        if state in TERMINAL_STATUSES:
            self._ledger.upsert(str(execution_id), status=str(state))
            log.info("执行 %s 服务端状态：%s（终态）", execution_id, state)
            return
        if record.status == "completion_pending" and frame.get("may_continue"):
            if str(frame.get("fencing_token")) != str(record.fencing_token) or str(frame.get("attempt_no")) != str(record.attempt_no):
                self._ledger.upsert(record.execution_id, status="failed")
                return
            next_index = _to_int(frame.get("next_chunk_index"))
            if next_index is None:
                log.warning("run.status 缺少 next_chunk_index，无法安全重放 %s", execution_id)
                return
            common = {"run_id": record.run_id, "execution_id": record.execution_id,
                      "attempt_no": record.attempt_no, "fencing_token": record.fencing_token}
            for index in range(max(0, next_index), len(record.chunks)):
                await self._send({"type": "run.delta", **common, "chunk_index": index, "text": record.chunks[index]})
            text = record.final_text or "".join(record.chunks)
            completion = {"type": "run.completed", **common, "last_chunk_index": len(record.chunks) - 1, "finish_reason": "stop"}
            if len(text.encode("utf-8")) <= FINAL_TEXT_MAX_BYTES:
                completion["final_text"] = text
            else:
                completion["content_hash"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            await self._send(completion)
            await self._send({"type": "run.query", "run_id": record.run_id, "execution_id": record.execution_id})
            return
        if frame.get("may_continue") and str(execution_id) not in self._active:
            # The adapter was interrupted, so explicitly terminate rather than
            # keeping a dead generation alive through connector heartbeats.
            await self._send({"type": "run.failed", "run_id": record.run_id,
                              "execution_id": record.execution_id, "attempt_no": record.attempt_no,
                              "fencing_token": record.fencing_token, "error_code": "CONNECTION_LOST",
                              "message": "连接中断导致生成停止，请显式重试", "side_effect_status": "none"})
            await self._send({"type": "run.query", "run_id": record.run_id, "execution_id": record.execution_id})
            return
        if state:
            self._ledger.upsert(str(execution_id), status=str(state))
        if frame.get("may_continue"):
            log.warning(
                "执行 %s 处于 %s 且 may_continue=true：本连接器无法续产输出（适配器不可恢复中断的生成），"
                "如需继续请人工处理或等待服务端回收",
                execution_id,
                state,
            )
        else:
            log.info("执行 %s 服务端状态：%s", execution_id, state)

    async def _handle_error_frame(self, frame: dict) -> None:
        code = frame.get("code")
        execution_id = frame.get("execution_id")
        log.warning("服务端错误帧：[%s] %s", code, frame.get("message"))
        run = self._active.get(str(execution_id)) if execution_id else None
        if code == "DELTA_GAP" and run is not None:
            # 缺片：按 next_chunk_index 补发已缓存的 chunks
            next_index = _to_int(frame.get("next_chunk_index"))
            if next_index is not None:
                for i in range(max(0, next_index), len(run.chunks)):
                    await self._send(
                        {
                            "type": "run.delta",
                            "run_id": run.run_id,
                            "execution_id": run.execution_id,
                            "attempt_no": run.attempt_no,
                            "fencing_token": run.fencing_token,
                            "chunk_index": i,
                            "text": run.chunks[i],
                        }
                    )
            return
        if code in STALE_ERROR_CODES and execution_id:
            record = self._ledger.get(str(execution_id))
            if record is not None and not record.is_terminal:
                self._ledger.upsert(str(execution_id), status="failed")
            if run is not None:
                run.stale = True
                if run.task and not run.task.done():
                    run.task.cancel()

    # ------------------------------------------------------------------ 恢复

    async def _resume_unfinished(self) -> None:
        for record in self._ledger.list_unfinished():
            log.info("重连恢复：查询未终态执行 %s（状态 %s）", record.execution_id, record.status)
            await self._send(
                {"type": "run.query", "run_id": record.run_id, "execution_id": record.execution_id}
            )

    async def _abort_active(self) -> None:
        """连接断开时：尽力停止适配器并取消所有在途任务（账本保持未终态，等重连恢复）。"""
        tasks: list[asyncio.Task] = []
        for run in list(self._active.values()):
            run.cancel_requested = True
            try:
                self.adapter.cancel()
            except Exception:
                log.debug("适配器 cancel 抛错", exc_info=True)
            if run.task is not None and not run.task.done():
                run.task.cancel()
                tasks.append(run.task)
        if tasks:
            await asyncio.wait(tasks, timeout=5)

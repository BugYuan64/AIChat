"""进程内实时枢纽：人类 WSS 连接注册表 + 连接器会话注册表 + 通知分发。
连接收到通知后自行从 inbox 表拉取并发送（拉模式，天然避免重复推送竞态）。"""

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger("aichat.realtime")


class HumanConnection:
    """一个已认证的人类 WSS 连接。drain() 由 hub 在数据就绪时调度。

    session_id 为签发票据的登录会话；撤销该会话时按它精准断开对应设备连接。
    """

    def __init__(self, account_id: str, drain, session_id: str | None = None, close=None) -> None:
        self.account_id = account_id
        self.session_id = session_id
        self._drain = drain
        self._close = close
        self.alive = True
        self.last_activity: datetime | None = None

    async def notify(self) -> None:
        if self.alive:
            try:
                await self._drain()
            except Exception:
                logger.exception("人类连接 drain 失败 account=%s", self.account_id)
                self.alive = False


class ConnectorConnection:
    def __init__(self, connector_id: str, agent_account_id: str, send) -> None:
        self.connector_id = connector_id
        self.agent_account_id = agent_account_id
        self._send = send
        self.alive = True

    async def send(self, frame: dict) -> bool:
        if not self.alive:
            return False
        try:
            await self._send(frame)
            return True
        except Exception:
            self.alive = False
            return False


class RealtimeHub:
    def __init__(self) -> None:
        self._humans: dict[str, set[HumanConnection]] = {}
        self._connectors: dict[str, ConnectorConnection] = {}
        self._lock = asyncio.Lock()

    async def add_human(self, conn: HumanConnection) -> None:
        async with self._lock:
            self._humans.setdefault(conn.account_id, set()).add(conn)

    async def remove_human(self, conn: HumanConnection) -> None:
        conn.alive = False
        async with self._lock:
            conns = self._humans.get(conn.account_id)
            if conns:
                conns.discard(conn)
                if not conns:
                    self._humans.pop(conn.account_id, None)

    async def kick_session(self, session_id: str) -> int:
        """撤销登录会话后断开其全部 WSS 连接；返回断开数量。"""
        kicked = 0
        closing = []
        async with self._lock:
            for conns in list(self._humans.values()):
                for conn in list(conns):
                    if conn.session_id == session_id:
                        conn.alive = False
                        conns.discard(conn)
                        if conn._close is not None:
                            closing.append(conn._close())
                        kicked += 1
        if closing:
            await asyncio.gather(*closing, return_exceptions=True)
        return kicked

    async def add_connector(self, conn: ConnectorConnection) -> ConnectorConnection | None:
        """新连接替换同 ID 旧连接（连接代次语义）；返回被替换的旧连接。"""
        async with self._lock:
            old = self._connectors.get(conn.connector_id)
            if old is not None:
                old.alive = False
            self._connectors[conn.connector_id] = conn
            return old

    async def remove_connector(self, conn: ConnectorConnection) -> None:
        conn.alive = False
        async with self._lock:
            if self._connectors.get(conn.connector_id) is conn:
                self._connectors.pop(conn.connector_id, None)

    def connector_online(self, connector_id: str) -> bool:
        conn = self._connectors.get(connector_id)
        return conn is not None and conn.alive

    async def send_to_connector(self, connector_id: str, frame: dict) -> bool:
        conn = self._connectors.get(connector_id)
        if conn is None or not conn.alive:
            return False
        return await conn.send(frame)

    async def notify_accounts(self, account_ids) -> None:
        """outbox 扇出完成后调用：让相关账号的在线连接拉取新事件。"""
        for account_id in set(account_ids):
            for conn in list(self._humans.get(account_id, ())):
                await conn.notify()

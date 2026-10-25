"""应用上下文：settings + db + hub + cipher + 取消标志 的单一容器，挂在 app.state.ctx。"""

import asyncio
from dataclasses import dataclass, field

from aichat.core.config import Settings
from aichat.core.db import Database
from aichat.core.ratelimit import SlidingWindowLimiter
from aichat.core.security import CredentialCipher
from aichat.modules.realtime.hub import RealtimeHub


class CancelFlags:
    """模型 API 执行的进程内取消标志（单实例；跨进程取消依赖 deadline 兜底）。"""

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}

    def cancel(self, run_id: str) -> None:
        event = self._events.get(run_id)
        if event is not None:
            event.set()

    def is_cancelled(self, run_id: str) -> bool:
        event = self._events.get(run_id)
        return event is not None and event.is_set()

    def register(self, run_id: str) -> asyncio.Event:
        event = asyncio.Event()
        self._events[run_id] = event
        return event

    def unregister(self, run_id: str) -> None:
        self._events.pop(run_id, None)


@dataclass
class AppContext:
    settings: Settings
    db: Database
    hub: RealtimeHub
    cipher: CredentialCipher
    cancel_flags: CancelFlags = field(default_factory=CancelFlags)
    limiter: SlidingWindowLimiter = field(default_factory=SlidingWindowLimiter)

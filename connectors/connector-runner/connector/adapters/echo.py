"""回声适配器：把收到的上下文逐字回显（联调与测试用）。"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator


class EchoAdapter:
    kind = "echo"

    def __init__(self, chunk_delay: float = 0.0) -> None:
        self._chunk_delay = chunk_delay
        self._cancelled = False

    async def run(
        self,
        context: list[dict],
        system_prompt: str | None,
        session_key: str | None = None,
        execution_policy: dict | None = None,
    ) -> AsyncIterator[str]:
        self._cancelled = False
        text = "\n".join(str(item.get("text", "")) for item in context)
        for ch in text:  # 逐字产出，模拟流式
            if self._cancelled:
                return
            if self._chunk_delay > 0:
                await asyncio.sleep(self._chunk_delay)
            yield ch

    def cancel(self) -> None:
        self._cancelled = True

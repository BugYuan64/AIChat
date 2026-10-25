"""适配器协议：把受限上下文转换为目标 Agent 调用并流式产出文本。

实现方须知：
- run() 是异步生成器：每次 yield 一段文本（一个 delta chunk），空串无意义应跳过；
- cancel() 应尽快让 run() 停止产出（尽力取消，不保证已停止的外部副作用）；
- 首版每个 Run 使用独立会话，禁止把一个群的上下文泄漏进另一个群。
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol


class AgentAdapter(Protocol):
    """外部 Agent 适配器协议。"""

    def run(self, context: list[dict], system_prompt: str | None) -> AsyncIterator[str]:
        """按上下文产出回复文本片段。context 元素形如
        {seq, sender_account_id, sender_kind, text, truncated}（契约 §7 run.offer）。"""
        ...

    def cancel(self) -> None:
        """请求取消当前 run()；尽力而为。"""
        ...

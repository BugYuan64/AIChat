"""适配器协议：把受限上下文转换为目标 Agent 调用并流式产出文本。

实现方须知：
- run() 是异步生成器：每次 yield 一段文本（一个 delta chunk），空串无意义应跳过；
- cancel() 应尽快让 run() 停止产出（尽力取消，不保证已停止的外部副作用）；
- session_key 标识"这是哪个对话"。有状态适配器（如托管的 CLI 会话）必须按
  session_key 维护独立会话，禁止把一个对话的上下文泄漏进另一个。
- context 是服务端固定的历史快照。**有状态适配器不应重放它**——历史已经活在
  外部 Agent 自己的会话里，重放会造成重复上下文。只取最新一条用户消息即可。
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol


class AgentAdapter(Protocol):
    """外部 Agent 适配器协议。"""

    def run(
        self,
        context: list[dict],
        system_prompt: str | None,
        session_key: str | None = None,
        execution_policy: dict | None = None,
    ) -> AsyncIterator[str]:
        """按上下文产出回复文本片段。context 元素形如
        {seq, sender_account_id, sender_kind, text, truncated}（契约 §7 run.offer）；
        session_key 通常是对话 ID；execution_policy 形如
        {permission_mode, workspace_dir}，由服务端按 AI 账号配置下发。"""
        ...

    def cancel(self) -> None:
        """请求取消当前 run()；尽力而为。"""
        ...

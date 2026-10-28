"""适配器注册与构建。新增适配器：实现 adapters.base.AgentAdapter 并在此注册。"""

from __future__ import annotations

from ..config import ConfigurationError
from ..ledger import Ledger
from .base import AgentAdapter
from .echo import EchoAdapter
from .openai_compatible import OpenAICompatibleAdapter
from .zcode import ZCodeAdapter

ADAPTER_KINDS = ("echo", "openai", "zcode")


def build_adapter(kind: str, *, ledger: Ledger | None = None) -> AgentAdapter:
    """按 adapter_kind 构建适配器实例。

    zcode 需要 ledger 来持久化会话索引（跨重启续接），因此调用方须传入。
    """
    if kind == "echo":
        return EchoAdapter()
    if kind == "openai":
        return OpenAICompatibleAdapter()
    if kind == "zcode":
        if ledger is None:
            raise ConfigurationError("zcode 适配器需要账本以保存会话索引")
        return ZCodeAdapter(ledger=ledger)
    raise ConfigurationError(
        f"未知适配器类型：{kind!r}（可选：{', '.join(ADAPTER_KINDS)}）"
    )

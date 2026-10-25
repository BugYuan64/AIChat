"""适配器注册与构建。新增适配器：实现 adapters.base.AgentAdapter 并在此注册。"""

from __future__ import annotations

from ..config import ConfigurationError
from .base import AgentAdapter
from .echo import EchoAdapter
from .openai_compatible import OpenAICompatibleAdapter

ADAPTER_KINDS = ("echo", "openai")


def build_adapter(kind: str) -> AgentAdapter:
    """按 adapter_kind 构建适配器实例。"""
    if kind == "echo":
        return EchoAdapter()
    if kind == "openai":
        return OpenAICompatibleAdapter()
    raise ConfigurationError(
        f"未知适配器类型：{kind!r}（可选：{', '.join(ADAPTER_KINDS)}）"
    )

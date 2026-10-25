"""runtime 适配层：把统一 Run 上下文转换为具体执行方式。

- model_api：后端 worker 直接调用 OpenAI 兼容 chat/completions（流式）
- connector：经 realtime 网关向外部连接器派发（见 modules/realtime/connector_gateway.py）

适配层只处理执行差异，不拥有账号、会话与权限。
"""

from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class ModelCallSpec:
    base_url: str
    api_key: str
    model: str
    system_prompt: str | None
    context: list[dict] = field(default_factory=list)  # [{role_hint, sender_kind, text}]
    timeout_seconds: int = 90
    max_tokens: int | None = None


class ProviderError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code  # provider_auth / quota_exhausted / overloaded / timeout / provider_error

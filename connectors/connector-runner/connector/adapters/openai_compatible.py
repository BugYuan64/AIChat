"""OpenAI 兼容 chat/completions 流式适配器。

配置来自环境变量（优先 AICHAT_ADAPTER_*，其次 OPENAI_*）：
- AICHAT_ADAPTER_API_KEY / OPENAI_API_KEY
- AICHAT_ADAPTER_BASE_URL / OPENAI_BASE_URL（默认 https://api.openai.com/v1）
- AICHAT_ADAPTER_MODEL / OPENAI_MODEL
"""

from __future__ import annotations

import json
import os
from typing import AsyncIterator

import httpx

from ..config import ConfigurationError

DEFAULT_BASE_URL = "https://api.openai.com/v1"


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


class OpenAICompatibleAdapter:
    kind = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or _first_env("AICHAT_ADAPTER_API_KEY", "OPENAI_API_KEY")
        self.base_url = (
            base_url
            or _first_env("AICHAT_ADAPTER_BASE_URL", "OPENAI_BASE_URL")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        self.model = model or _first_env("AICHAT_ADAPTER_MODEL", "OPENAI_MODEL")
        if not self.api_key:
            raise ConfigurationError(
                "openai 适配器缺少 API Key：设置 AICHAT_ADAPTER_API_KEY 或 OPENAI_API_KEY"
            )
        if not self.model:
            raise ConfigurationError(
                "openai 适配器缺少模型名：设置 AICHAT_ADAPTER_MODEL 或 OPENAI_MODEL"
            )
        self._cancelled = False
        self._client = httpx.AsyncClient(timeout=timeout)

    async def run(
        self,
        context: list[dict],
        system_prompt: str | None,
        session_key: str | None = None,
        execution_policy: dict | None = None,
    ) -> AsyncIterator[str]:
        self._cancelled = False
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        for item in context:
            role = "assistant" if item.get("sender_kind") == "ai" else "user"
            messages.append({"role": role, "content": str(item.get("text", ""))})

        payload = {"model": self.model, "messages": messages, "stream": True}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with self._client.stream(
            "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
        ) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode("utf-8", "replace")
                raise RuntimeError(f"上游模型服务返回 HTTP {resp.status_code}: {body[:200]}")
            async for line in resp.aiter_lines():
                if self._cancelled:
                    break
                line = line.strip()
                if not line or line.startswith(":"):  # SSE 注释/心跳
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0].get("delta") or {}).get("content")
                if delta:
                    yield delta

    def cancel(self) -> None:
        self._cancelled = True

    async def aclose(self) -> None:
        await self._client.aclose()

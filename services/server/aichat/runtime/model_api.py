"""OpenAI 兼容 chat/completions 流式适配器（协议 openai_chat）。"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from aichat.runtime.base import ModelCallSpec, ProviderError


def _map_status_error(status_code: int) -> str:
    if status_code in (401, 403):
        return "provider_auth"
    if status_code in (402, 429):
        return "quota_exhausted"
    if status_code >= 500:
        return "overloaded"
    return "provider_error"


def _build_messages(spec: ModelCallSpec) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if spec.system_prompt:
        messages.append({"role": "system", "content": spec.system_prompt})
    for item in spec.context:
        text = item.get("text") or ""
        if not text:
            continue
        role = "assistant" if item.get("sender_kind") == "ai" else "user"
        messages.append({"role": role, "content": text})
    return messages


async def stream_chat(spec: ModelCallSpec) -> AsyncIterator[str]:
    """产出文本增量；在流上抛 ProviderError。"""
    url = spec.base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": spec.model,
        "messages": _build_messages(spec),
        "stream": True,
    }
    if spec.max_tokens:
        payload["max_tokens"] = spec.max_tokens
    try:
        async with httpx.AsyncClient(timeout=spec.timeout_seconds) as client:
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers={"Authorization": f"Bearer {spec.api_key}",
                         "Content-Type": "application/json"},
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise ProviderError(_map_status_error(response.status_code),
                                        f"供应商返回 {response.status_code}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        if data == "[DONE]":
                            return
                        continue
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content")
                    if text:
                        yield text
    except httpx.TimeoutException:
        raise ProviderError("timeout", "模型调用超时")
    except httpx.HTTPError as exc:
        raise ProviderError("provider_error", f"模型调用失败: {type(exc).__name__}")


async def test_connection(spec: ModelCallSpec) -> None:
    """小额连接测试：请求一个极短补全。"""
    probe = ModelCallSpec(
        base_url=spec.base_url,
        api_key=spec.api_key,
        model=spec.model,
        system_prompt=None,
        context=[{"sender_kind": "human", "text": "ping"}],
        timeout_seconds=30,
        max_tokens=1,
    )
    buffer: list[str] = []
    async for piece in stream_chat(probe):
        buffer.append(piece)
        break  # 只取第一片即可

"""回声适配器测试：逐字产出、多消息拼接、cancel 生效。"""

import asyncio

from connector.adapters.echo import EchoAdapter


def _ctx(*texts):
    return [
        {"seq": str(i), "sender_account_id": "u1", "sender_kind": "human", "text": t}
        for i, t in enumerate(texts)
    ]


async def test_yields_context_text_char_by_char():
    adapter = EchoAdapter()
    pieces = [p async for p in adapter.run(_ctx("你好ab"), None)]
    assert "".join(pieces) == "你好ab"
    assert all(len(p) == 1 for p in pieces)  # 逐字产出


async def test_multiple_context_messages_joined_by_newline():
    adapter = EchoAdapter()
    pieces = [p async for p in adapter.run(_ctx("a", "b"), None)]
    assert "".join(pieces) == "a\nb"


async def test_ignores_system_prompt():
    adapter = EchoAdapter()
    pieces = [p async for p in adapter.run(_ctx("x"), "你是助手")]
    assert "".join(pieces) == "x"


async def test_cancel_stops_production():
    adapter = EchoAdapter(chunk_delay=0.001)
    gen = adapter.run(_ctx("0123456789"), None)
    first = await gen.__anext__()
    assert first == "0"
    adapter.cancel()
    rest = [p async for p in gen]
    assert rest == []


async def test_cancel_is_best_effort_before_start():
    adapter = EchoAdapter()
    adapter.cancel()
    gen = adapter.run(_ctx("abc"), None)
    # 新一次 run 开始时会复位取消标志（会话内多 Run 串行）
    pieces = [p async for p in gen]
    assert "".join(pieces) == "abc"


def test_kind():
    assert EchoAdapter.kind == "echo"

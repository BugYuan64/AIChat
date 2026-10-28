"""zcode 适配器与账本会话索引的单元测试。

不依赖真实 zcode：用假的可执行脚本模拟 CLI 输出（含噪声行、JSON 结果）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from connector.ledger import Ledger


@pytest.fixture()
def ledger(tmp_path):
    led = Ledger(tmp_path / "ledger.sqlite3")
    yield led
    led.close()


# ---------------------------------------------------------------- 账本会话索引


def test_session_defaults_to_empty(ledger):
    assert ledger.get_session("conv-1", "zcode") is None


def test_session_roundtrip(ledger):
    ledger.save_session("conv-1", "zcode", external_session_id="sess_abc", cwd="/srv/x")
    rec = ledger.get_session("conv-1", "zcode")
    assert rec is not None
    assert rec.external_session_id == "sess_abc"
    assert rec.cwd == "/srv/x"


def test_session_is_namespaced_by_adapter_kind(ledger):
    ledger.save_session("conv-1", "zcode", external_session_id="sess_z")
    ledger.save_session("conv-1", "codex", external_session_id="sess_c")
    assert ledger.get_session("conv-1", "zcode").external_session_id == "sess_z"
    assert ledger.get_session("conv-1", "codex").external_session_id == "sess_c"


def test_save_session_preserves_existing_id_when_not_given(ledger):
    ledger.save_session("conv-1", "zcode", external_session_id="sess_keep", cwd="/a")
    ledger.save_session("conv-1", "zcode", cwd="/b")
    rec = ledger.get_session("conv-1", "zcode")
    assert rec.external_session_id == "sess_keep"
    assert rec.cwd == "/b"


def test_clear_session(ledger):
    ledger.save_session("conv-1", "zcode", external_session_id="sess_x")
    ledger.clear_session("conv-1", "zcode")
    assert ledger.get_session("conv-1", "zcode") is None


# ---------------------------------------------------------------- 输出解析


def test_parse_skips_noise_lines():
    from connector.adapters.zcode import _parse_json_payload

    output = (
        "ZCode Built-in skipped (not-due)\n"
        '{\n'
        '  "sessionId": "sess_1",\n'
        '  "response": "hello"\n'
        "}\n"
    )
    payload = _parse_json_payload(output)
    assert payload is not None
    assert payload["sessionId"] == "sess_1"
    assert payload["response"] == "hello"


def test_parse_returns_none_for_garbage():
    from connector.adapters.zcode import _parse_json_payload

    assert _parse_json_payload("no json here\nstill nothing") is None


def test_parse_handles_leading_blank_and_indented_json():
    from connector.adapters.zcode import _parse_json_payload

    output = '\n\n   {\n "sessionId": "sess_2", "response": "ok"\n}\n'
    payload = _parse_json_payload(output)
    assert payload is not None and payload["sessionId"] == "sess_2"


# ---------------------------------------------------------------- 指令提取


def test_last_user_text_ignores_ai_messages():
    from connector.adapters.zcode import _last_user_text

    context = [
        {"sender_kind": "human", "text": "第一条"},
        {"sender_kind": "ai", "text": "回复一"},
        {"sender_kind": "human", "text": "第二条"},
    ]
    assert _last_user_text(context) == "第二条"


def test_last_user_text_falls_back_to_ai_when_only_ai():
    from connector.adapters.zcode import _last_user_text

    assert _last_user_text([{"sender_kind": "ai", "text": "只有 AI"}]) == "只有 AI"


def test_last_user_text_empty_context():
    from connector.adapters.zcode import _last_user_text

    assert _last_user_text([]) == ""


# ---------------------------------------------------------------- 权限模式


def test_default_mode_is_conservative_plan():
    from connector.adapters.zcode import DEFAULT_MODE

    # 绝不能继承 `zcode -p` 自身的 yolo 默认值
    assert DEFAULT_MODE == "plan"


def test_invalid_mode_rejected(ledger):
    from connector.adapters.zcode import ZCodeAdapter
    from connector.config import ConfigurationError

    with pytest.raises(ConfigurationError):
        ZCodeAdapter(ledger=ledger, mode="danger")


# ---------------------------------------------------------------- 端到端（假 CLI）


def _write_fake_cli(tmp_path: Path, payload: str) -> list[str]:
    """写一个假 zcode：打印噪声行 + 给定 JSON，并记录收到的参数。返回 argv 列表。"""
    script = tmp_path / "fake_zcode.py"
    args_file = tmp_path / "args.txt"
    script.write_text(
        "import sys, pathlib\n"
        f"pathlib.Path({str(args_file)!r}).write_text('\\n'.join(sys.argv[1:]), encoding='utf-8')\n"
        "print('ZCode Built-in skipped (not-due)')\n"
        f"print({payload!r})\n",
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


@pytest.mark.asyncio
async def test_adapter_captures_and_reuses_session(tmp_path, ledger):
    from connector.adapters.zcode import ZCodeAdapter

    cli = _write_fake_cli(
        tmp_path, '{"sessionId": "sess_new", "response": "hi there"}'
    )
    adapter = ZCodeAdapter(ledger=ledger, binary=cli, cwd=str(tmp_path / "work"))
    chunks = [c async for c in adapter.run([{"sender_kind": "human", "text": "你好"}], None, "conv-9")]
    assert "".join(chunks) == "hi there"
    assert ledger.get_session("conv-9", "zcode").external_session_id == "sess_new"


@pytest.mark.asyncio
async def test_adapter_passes_resume_on_second_run(tmp_path, ledger):
    from connector.adapters.zcode import ZCodeAdapter

    cli = _write_fake_cli(
        tmp_path, '{"sessionId": "sess_new", "response": "ok"}'
    )
    adapter = ZCodeAdapter(ledger=ledger, binary=cli, cwd=str(tmp_path / "work"))
    async for _ in adapter.run([{"sender_kind": "human", "text": "一"}], None, "conv-r"):
        pass
    async for _ in adapter.run([{"sender_kind": "human", "text": "二"}], None, "conv-r"):
        pass
    args = (tmp_path / "args.txt").read_text(encoding="utf-8")
    assert "--resume" in args
    assert "sess_new" in args


@pytest.mark.asyncio
async def test_adapter_uses_plan_mode_by_default(tmp_path, ledger):
    from connector.adapters.zcode import ZCodeAdapter

    cli = _write_fake_cli(tmp_path, '{"sessionId": "sess_m", "response": "x"}')
    adapter = ZCodeAdapter(ledger=ledger, binary=cli, cwd=str(tmp_path / "work"))
    async for _ in adapter.run([{"sender_kind": "human", "text": "go"}], None, "conv-m"):
        pass
    args = (tmp_path / "args.txt").read_text(encoding="utf-8")
    assert "--mode" in args
    assert "plan" in args
    assert "yolo" not in args


@pytest.mark.asyncio
async def test_adapter_drops_stale_session_when_resume_fails(tmp_path, ledger):
    """续接失败（CLI 拒绝 --resume）时应清索引并新建会话重试一次。"""
    from connector.adapters.zcode import ZCodeAdapter

    ledger.save_session("conv-stale", "zcode", external_session_id="sess_gone")
    script = tmp_path / "fake_cli.py"
    args_file = tmp_path / "args.txt"
    script.write_text(
        "import sys, pathlib\n"
        "args = sys.argv[1:]\n"
        f"pathlib.Path({str(args_file)!r}).write_text('\\n'.join(args), encoding='utf-8')\n"
        "if '--resume' in args:\n"
        "    print('session not found')\n"
        "    sys.exit(1)\n"
        "print('{\"sessionId\": \"sess_fresh\", \"response\": \"recovered\"}')\n",
        encoding="utf-8",
    )
    adapter = ZCodeAdapter(ledger=ledger, binary=[sys.executable, str(script)],
                           cwd=str(tmp_path / "work"))
    chunks = [c async for c in adapter.run([{"sender_kind": "human", "text": "继续"}], None, "conv-stale")]
    assert "".join(chunks) == "recovered"
    assert ledger.get_session("conv-stale", "zcode").external_session_id == "sess_fresh"


# ---------------------------------------------------------------- 服务端下发的执行策略


def test_policy_from_server_overrides_adapter_default(ledger, tmp_path):
    """服务端下发的 permission_mode 必须覆盖适配器自己的配置。"""
    from connector.adapters.zcode import ZCodeAdapter

    adapter = ZCodeAdapter(ledger=ledger, mode="plan", cwd=str(tmp_path / "a"))
    mode, cwd = adapter._resolve_policy({"permission_mode": "edit", "workspace_dir": str(tmp_path / "b")})
    assert mode == "edit"
    assert str(cwd).endswith("b")


def test_policy_falls_back_to_adapter_config(ledger, tmp_path):
    from connector.adapters.zcode import ZCodeAdapter

    adapter = ZCodeAdapter(ledger=ledger, mode="guarded", cwd=str(tmp_path / "c"))
    mode, cwd = adapter._resolve_policy(None)
    assert mode == "guarded"
    assert str(cwd).endswith("c")


def test_unknown_mode_from_server_falls_back_to_plan(ledger, tmp_path):
    """服务端下发了不认识的模式时，必须保守回退到 plan 而不是放行。"""
    from connector.adapters.zcode import ZCodeAdapter

    adapter = ZCodeAdapter(ledger=ledger, mode="edit", cwd=str(tmp_path / "d"))
    mode, _ = adapter._resolve_policy({"permission_mode": "root-everything"})
    assert mode == "plan"


@pytest.mark.asyncio
async def test_adapter_passes_server_mode_to_cli(tmp_path, ledger):
    """端到端：服务端说 edit，命令行里就应该是 --mode edit。"""
    from connector.adapters.zcode import ZCodeAdapter

    cli = _write_fake_cli(tmp_path, '{"sessionId": "sess_p", "response": "done"}')
    adapter = ZCodeAdapter(ledger=ledger, binary=cli, mode="plan", cwd=str(tmp_path / "work"))
    chunks = [
        c
        async for c in adapter.run(
            [{"sender_kind": "human", "text": "改一下"}],
            None,
            "conv-policy",
            {"permission_mode": "edit", "workspace_dir": str(tmp_path / "proj")},
        )
    ]
    assert "".join(chunks) == "done"
    args = (tmp_path / "args.txt").read_text(encoding="utf-8")
    assert "--mode" in args and "edit" in args

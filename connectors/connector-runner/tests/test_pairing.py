"""配对状态机测试：轮询解析、退避计算、终态映射与全流程（假 httpx transport）。"""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from connector.config import ServerConfig
from connector.pairing import (
    PairingAborted,
    PairingClient,
    PairingError,
    interpret_poll,
    next_poll_delay,
)


def status_payload(status: str, **extra) -> dict:
    return {"request_id": "r", "data": {"status": status, **extra}}


def error_payload(code: str, retry_after_ms: int | None = None) -> dict:
    err = {"code": code, "message": "err", "retryable": True}
    if retry_after_ms is not None:
        err["retry_after_ms"] = retry_after_ms
    return {"request_id": "r", "error": err}


# ---------------------------------------------------------------- 轮询解析


class TestInterpretPoll:
    def test_pending_user_waits(self):
        assert interpret_poll(status_payload("pending_user")).action == "wait"

    def test_pending_local_carries_display_info(self):
        result = interpret_poll(
            status_payload(
                "pending_local",
                owner_display_name="张三",
                agent_display_name="小助",
                confirm_code="123456",
            )
        )
        assert result.action == "pending_local"
        assert result.owner_display_name == "张三"
        assert result.agent_display_name == "小助"
        assert result.confirm_code == "123456"
        assert not result.terminal

    def test_approved(self):
        result = interpret_poll(status_payload("approved"))
        assert result.action == "approved"
        assert not result.terminal

    @pytest.mark.parametrize("status", ["denied", "expired", "cancelled", "redeemed"])
    def test_terminal_statuses(self, status):
        # 状态机内可直出的终态（revoked/consumed 仅以错误码出现，见下方映射测试）
        result = interpret_poll(status_payload(status))
        assert result.action == status
        assert result.terminal

    def test_unknown_status_rejected(self):
        with pytest.raises(PairingError):
            interpret_poll(status_payload("wat"))

    def test_slow_down_error(self):
        result = interpret_poll(error_payload("SLOW_DOWN", retry_after_ms=1500))
        assert result.action == "slow_down"
        assert result.retry_after_ms == 1500

    def test_rate_limited_without_retry_after(self):
        result = interpret_poll(error_payload("RATE_LIMITED"))
        assert result.action == "slow_down"
        assert result.retry_after_ms is None

    def test_pairing_pending_error_maps_to_wait(self):
        assert interpret_poll(error_payload("PAIRING_PENDING")).action == "wait"

    @pytest.mark.parametrize(
        "code,status",
        [
            ("PAIRING_DENIED", "denied"),
            ("PAIRING_EXPIRED", "expired"),
            ("PAIRING_REVOKED", "revoked"),
            ("PAIRING_CONSUMED", "consumed"),
        ],
    )
    def test_pairing_terminal_error_codes(self, code, status):
        result = interpret_poll(error_payload(code))
        assert result.action == status
        assert result.terminal

    def test_unexpected_error_code_raises(self):
        with pytest.raises(PairingError):
            interpret_poll(error_payload("VALIDATION_FAILED"))

    def test_malformed_payload_raises(self):
        with pytest.raises(PairingError):
            interpret_poll({"stray": True})


class TestNextPollDelay:
    def test_normal_uses_interval(self):
        assert next_poll_delay(5.0, interpret_poll(status_payload("pending_user"))) == 5.0

    def test_slow_down_uses_retry_after(self):
        result = interpret_poll(error_payload("SLOW_DOWN", retry_after_ms=3000))
        assert next_poll_delay(5.0, result) == 3.0

    def test_slow_down_minimum_one_second(self):
        result = interpret_poll(error_payload("SLOW_DOWN", retry_after_ms=10))
        assert next_poll_delay(5.0, result) == 1.0

    def test_slow_down_without_hint_doubles_interval(self):
        result = interpret_poll(error_payload("RATE_LIMITED"))
        assert next_poll_delay(5.0, result) == 10.0


# ---------------------------------------------------------------- 全流程（假服务端）


def make_fake_backend():
    """RFC8628 风格假服务端：slow_down 一次 → pending_user → pending_local
    （本机确认后）→ approved → 兑换。"""
    state = {
        "status": "pending_user",
        "confirmed": False,
        "redeemed": False,
        "status_calls": 0,
        "slowdown_left": 1,
        "requests": [],
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content or b"{}")
        state["requests"].append((path, body))
        now = datetime.now(timezone.utc)

        if path == "/v1/pairings":
            return httpx.Response(
                201,
                json={
                    "request_id": "r",
                    "data": {
                        "pairing_id": "p1",
                        "short_code": "AB12CD34",
                        "qr_payload": "https://srv.example/pair?pid=p1&code=AB12CD34",
                        "confirm_code": "123456",
                        "device_code": "dev-secret",
                        "expires_at": (now + timedelta(minutes=5)).isoformat(),
                        "interval_seconds": 0,
                    },
                },
            )
        if path == "/v1/pairing-status":
            assert body.get("device_code") == "dev-secret"  # device_code 只在 body
            if state["slowdown_left"] > 0:
                state["slowdown_left"] -= 1
                return httpx.Response(429, json=error_payload("SLOW_DOWN", retry_after_ms=5))
            state["status_calls"] += 1
            if state["status"] == "pending_user" and state["status_calls"] >= 1:
                state["status"] = "pending_local"
            elif state["status"] == "pending_local" and state["confirmed"]:
                state["status"] = "approved"
            data = {"status": state["status"]}
            if state["status"] == "pending_local":
                data.update(
                    owner_display_name="张三",
                    agent_display_name="小助",
                    confirm_code="123456",
                )
            return httpx.Response(200, json={"request_id": "r", "data": data})
        if path == "/v1/pairing-local-confirmation":
            assert body == {"device_code": "dev-secret", "confirmed": True}
            state["confirmed"] = True
            return httpx.Response(200, json={"request_id": "r", "data": {"status": "approved"}})
        if path == "/v1/pairing-token":
            if state["redeemed"]:
                return httpx.Response(409, json=error_payload("PAIRING_CONSUMED"))
            state["redeemed"] = True
            return httpx.Response(
                200,
                json={
                    "request_id": "r",
                    "data": {
                        "connector_id": "c1",
                        "agent_id": "agent-1",
                        "access_token": "at-1",
                        "refresh_credential": "rc-1",
                        "expires_in": 900,
                    },
                },
            )
        return httpx.Response(404, json=error_payload("NOT_FOUND"))

    return handler, state


async def _nosleep(_delay: float) -> None:
    return None


@pytest.fixture()
def config(tmp_path):
    return ServerConfig(
        server_base_url="https://srv.example",
        credentials_path=tmp_path / "credentials.json",
        ledger_path=tmp_path / "ledger.sqlite3",
    )


async def test_full_pairing_flow(config):
    handler, state = make_fake_backend()
    qr_seen: list[str] = []
    prompts: list[str] = []
    messages: list[str] = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = PairingClient(
        config,
        http,
        confirm_prompt=lambda detail: (prompts.append(detail), True)[1],
        render_qr=qr_seen.append,
        sleep=_nosleep,
        output=messages.append,
    )
    try:
        creds = await client.run_pairing(
            agent_id="agent-1",
            connector_name="测试连接器",
            adapter_kind="echo",
            platform="test",
            requested_capabilities=["chat.text"],
        )
    finally:
        await http.aclose()

    assert creds["connector_id"] == "c1"
    assert creds["agent_id"] == "agent-1"
    assert creds["access_token"] == "at-1"
    assert creds["refresh_credential"] == "rc-1"
    assert creds["server_base_url"] == "https://srv.example"
    assert creds["adapter_kind"] == "echo"
    assert creds["paired_at"]

    # 二维码只含配对入口与非秘密短码；device_code 不出现
    assert qr_seen == ["https://srv.example/pair?pid=p1&code=AB12CD34"]
    assert all("dev-secret" not in m for m in messages)

    # 创建请求体按契约 §7
    create_path, create_body = state["requests"][0]
    assert create_path == "/v1/pairings"
    assert create_body == {
        "agent_id": "agent-1",
        "connector_name": "测试连接器",
        "platform": "test",
        "adapter_kind": "echo",
        "requested_capabilities": ["chat.text"],
    }
    # 状态轮询与确认、兑换的顺序
    paths = [p for p, _ in state["requests"]]
    assert paths.count("/v1/pairing-status") >= 3
    assert "/v1/pairing-local-confirmation" in paths
    assert paths[-1] == "/v1/pairing-token"
    # pending_local 提示包含所有者/AI 名与确认码
    assert any("张三" in p and "小助" in p and "123456" in p for p in prompts)


async def test_local_confirmation_denied_aborts(config):
    handler, _state = make_fake_backend()
    qr_seen: list[str] = []
    messages: list[str] = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = PairingClient(
        config,
        http,
        confirm_prompt=lambda detail: False,  # 本机操作者拒绝
        render_qr=qr_seen.append,
        sleep=_nosleep,
        output=messages.append,
    )
    try:
        with pytest.raises(PairingAborted):
            await client.run_pairing(
                agent_id="agent-1",
                connector_name="n",
                adapter_kind="echo",
                platform="test",
                requested_capabilities=[],
            )
    finally:
        await http.aclose()


async def test_confirm_code_mismatch_aborts(config):
    """pending_local 返回的确认码与创建时不一致 → 疑似异常，中止。"""
    handler, _state = make_fake_backend()

    async def mismatch_handler(request: httpx.Request) -> httpx.Response:
        response = await handler(request)
        if request.url.path == "/v1/pairing-status" and response.status_code == 200:
            payload = json.loads(response.content)
            if payload.get("data", {}).get("status") == "pending_local":
                payload["data"]["confirm_code"] = "999999"
                return httpx.Response(200, json=payload, headers=response.headers)
        return response

    http = httpx.AsyncClient(transport=httpx.MockTransport(mismatch_handler))
    client = PairingClient(
        config,
        http,
        confirm_prompt=lambda detail: True,
        render_qr=lambda p: None,
        sleep=_nosleep,
        output=lambda m: None,
    )
    try:
        with pytest.raises(PairingError, match="确认码不一致"):
            await client.run_pairing(
                agent_id="agent-1",
                connector_name="n",
                adapter_kind="echo",
                platform="test",
                requested_capabilities=[],
            )
    finally:
        await http.aclose()


async def test_denied_status_raises_clear_error(config):
    handler, _state = make_fake_backend()

    async def denied_handler(request: httpx.Request) -> httpx.Response:
        response = await handler(request)
        if request.url.path == "/v1/pairing-status" and response.status_code == 200:
            payload = json.loads(response.content)
            if payload.get("data", {}).get("status") != "pending_local":
                payload["data"]["status"] = "denied"
                return httpx.Response(200, json=payload, headers=response.headers)
        return response

    http = httpx.AsyncClient(transport=httpx.MockTransport(denied_handler))
    client = PairingClient(
        config,
        http,
        confirm_prompt=lambda detail: True,
        render_qr=lambda p: None,
        sleep=_nosleep,
        output=lambda m: None,
    )
    try:
        with pytest.raises(PairingError, match="denied"):
            await client.run_pairing(
                agent_id="agent-1",
                connector_name="n",
                adapter_kind="echo",
                platform="test",
                requested_capabilities=[],
            )
    finally:
        await http.aclose()

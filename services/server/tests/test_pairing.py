"""D4 配对设备流：pending_user → pending_local → approved → redeemed + 兑换竞争。"""

import pytest

from tests.conftest import make_admin, register_user


async def _setup_agent(client, ctx):
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")
    ha = {"Authorization": f"Bearer {alice['token']}"}
    resp = await client.post("/v1/agents", json={
        "handle": "writer-ai", "display_name": "写作助手",
    }, headers=ha)
    agent_id = resp.json()["data"]["account_id"]
    return alice, ha, agent_id


@pytest.mark.asyncio
async def test_pairing_qr_uses_configured_public_domain(client, ctx):
    _, _, agent_id = await _setup_agent(client, ctx)
    ctx.settings.public_base_url = "https://aichat.wsnbb.shop/"
    created = await client.post("/v1/pairings", json={
        "agent_id": agent_id, "connector_name": "Domain test", "adapter_kind": "echo",
    })
    assert created.status_code == 201
    assert created.json()["data"]["qr_payload"].startswith("https://aichat.wsnbb.shop/pair?")


@pytest.mark.asyncio
async def test_full_pairing_flow(client, ctx):
    alice, ha, agent_id = await _setup_agent(client, ctx)

    created = await client.post("/v1/pairings", json={
        "agent_id": agent_id, "connector_name": "办公电脑", "platform": "windows",
        "adapter_kind": "echo",
    })
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    pairing_id, device_code = data["pairing_id"], data["device_code"]
    assert data["short_code"] and data["confirm_code"] and data["qr_payload"]
    assert "device_code" not in data["qr_payload"]

    # App 扫码查看（需登录 + 短码）
    view = await client.get(f"/v1/pairings/{pairing_id}",
                            params={"code": data["short_code"]}, headers=ha)
    assert view.status_code == 200
    assert view.json()["data"]["confirm_code"] == data["confirm_code"]

    # 错误确认码 → 400
    wrong = await client.post(f"/v1/pairings/{pairing_id}/decision", json={
        "decision": "approve", "confirm_code": "000000", "expected_version": 1,
    }, headers=ha)
    assert wrong.status_code == 400

    # 正确确认码 + 版本 → pending_local
    ok = await client.post(f"/v1/pairings/{pairing_id}/decision", json={
        "decision": "approve", "confirm_code": data["confirm_code"], "expected_version": 1,
    }, headers=ha)
    assert ok.status_code == 200
    assert ok.json()["data"]["status"] == "pending_local"

    # 连接器轮询：看到批准方信息供本机核对
    status = await client.post("/v1/pairing-status", json={"device_code": device_code})
    assert status.status_code == 200
    assert status.json()["data"]["status"] == "pending_local"
    assert status.json()["data"]["confirm_code"] == data["confirm_code"]

    # 本机确认 → 兑换
    confirmed = await client.post("/v1/pairing-local-confirmation",
                                  json={"device_code": device_code, "confirmed": True})
    assert confirmed.json()["data"]["status"] == "approved"

    redeemed = await client.post("/v1/pairing-token", json={"device_code": device_code})
    assert redeemed.status_code == 200, redeemed.text
    tokens = redeemed.json()["data"]
    assert tokens["connector_id"] and tokens["access_token"] and tokens["refresh_credential"]

    # 二次兑换 → 409 PAIRING_CONSUMED
    again = await client.post("/v1/pairing-token", json={"device_code": device_code})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "PAIRING_CONSUMED"

    # 刷新访问令牌
    refreshed = await client.post("/v1/connectors/access-tokens",
                                  json={"refresh_credential": tokens["refresh_credential"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["data"]["access_token"]

    # 绑定已切换为 connector 且启用
    agent_view = await client.get(f"/v1/agents/{agent_id}", headers=ha)
    binding = agent_view.json()["data"]["binding"]
    assert binding["mode"] == "connector" and binding["enabled"] is True

    # 所有者可撤销连接器
    revoke = await client.post(f"/v1/connectors/{tokens['connector_id']}/revoke",
                               json={"reason": "设备遗失"}, headers=ha)
    assert revoke.status_code == 200
    revoked_refresh = await client.post("/v1/connectors/access-tokens",
                                        json={"refresh_credential": tokens["refresh_credential"]})
    assert revoked_refresh.status_code == 403


@pytest.mark.asyncio
async def test_pairing_expired_and_denied(client, ctx):
    from datetime import timedelta

    alice, ha, agent_id = await _setup_agent(client, ctx)
    created = await client.post("/v1/pairings", json={
        "agent_id": agent_id, "connector_name": "x", "platform": "linux", "adapter_kind": "echo",
    })
    data = created.json()["data"]

    # 过期后轮询 → PAIRING_EXPIRED
    async with ctx.db.session_factory() as session:
        from aichat.modules.pairing.models import PairingSession

        pairing = await session.get(PairingSession, data["pairing_id"])
        pairing.expires_at = pairing.expires_at - timedelta(minutes=10)
        await session.commit()

    status = await client.post("/v1/pairing-status", json={"device_code": data["device_code"]})
    assert status.status_code == 400
    assert status.json()["error"]["code"] == "PAIRING_EXPIRED"

    # 拒绝路径
    created2 = await client.post("/v1/pairings", json={
        "agent_id": agent_id, "connector_name": "y", "platform": "linux", "adapter_kind": "echo",
    })
    data2 = created2.json()["data"]
    denied = await client.post(f"/v1/pairings/{data2['pairing_id']}/decision", json={
        "decision": "deny", "confirm_code": data2["confirm_code"], "expected_version": 1,
    }, headers=ha)
    assert denied.json()["data"]["status"] == "denied"
    redeem = await client.post("/v1/pairing-token", json={"device_code": data2["device_code"]})
    assert redeem.status_code == 400

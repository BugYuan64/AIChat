"""D1 身份链路：邀请注册、登录、刷新轮换、退出、票据。"""

import pytest

from tests.conftest import make_admin, register_user


@pytest.mark.asyncio
async def test_register_login_refresh_logout(client, ctx):
    _, invites = await make_admin(ctx)

    resp = await client.post("/v1/auth/register", json={
        "invite_code": "bad-code", "handle": "alice", "display_name": "Alice",
        "password": "password-123456",
    })
    assert resp.status_code == 400

    alice = await register_user(client, invites[0], "alice")
    assert alice["account_id"]

    # 错误密码
    bad = await client.post("/v1/auth/login", json={"handle": "alice", "password": "wrong-password-1"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "AUTH_INVALID"

    # 重复占用账号名
    resp = await client.post("/v1/auth/register", json={
        "invite_code": invites[1], "handle": "alice", "display_name": "X", "password": "password-123456",
    })
    assert resp.status_code == 400

    me = await client.get("/v1/me", headers={"Authorization": f"Bearer {alice['token']}"})
    assert me.status_code == 200
    assert me.json()["data"]["handle"] == "alice"

    # 刷新轮换：旧 refresh 二次使用失败
    login = await client.post("/v1/auth/login", json={"handle": "alice", "password": "password-123456"})
    refresh_token = login.json()["data"]["refresh_token"]
    first = await client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert first.status_code == 200
    second = await client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert second.status_code == 401

    # 退出后旧访问令牌失效
    new_token = first.json()["data"]["access_token"]
    logout = await client.post("/v1/auth/logout", headers={"Authorization": f"Bearer {new_token}"})
    assert logout.status_code == 200
    me = await client.get("/v1/me", headers={"Authorization": f"Bearer {new_token}"})
    assert me.status_code == 401
    assert me.json()["error"]["code"] == "SESSION_REVOKED"


@pytest.mark.asyncio
async def test_ws_ticket_flow(client, ctx):
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")

    ticket = await client.post("/v1/realtime-tickets", json={"audience": "human_events"},
                               headers={"Authorization": f"Bearer {alice['token']}"})
    assert ticket.status_code == 200
    value = ticket.json()["data"]["ticket"]

    # 一次性：同票据不能兑换两次（直接走服务层验证）
    from aichat.modules.identity.service import IdentityService

    async with ctx.db.session_factory() as session:
        service = IdentityService(ctx, session)
        account_id, session_id = await service.consume_ws_ticket(value, "human_events")
        assert account_id == alice["account_id"]
        assert session_id  # 人类票据绑定登录会话
        with pytest.raises(Exception):
            await service.consume_ws_ticket(value, "human_events")
        await session.commit()


@pytest.mark.asyncio
async def test_profile_update(client, ctx):
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")
    ha = {"Authorization": f"Bearer {alice['token']}"}

    patched = await client.patch("/v1/me", json={
        "display_name": "爱丽丝", "bio": "一句话简介",
    }, headers=ha)
    assert patched.status_code == 200
    assert patched.json()["data"]["display_name"] == "爱丽丝"
    assert patched.json()["data"]["bio"] == "一句话简介"

    # 空昵称被拒
    bad = await client.patch("/v1/me", json={"display_name": ""}, headers=ha)
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_session_management(client, ctx):
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")  # 设备 A

    # 设备 B 再登录一次
    second = await client.post("/v1/auth/login", json={
        "handle": "alice", "password": "password-123456", "device_summary": "Pixel 8",
    })
    assert second.status_code == 200
    hb = {"Authorization": f"Bearer {second.json()['data']['access_token']}"}

    ha = {"Authorization": f"Bearer {alice['token']}"}
    sessions = await client.get("/v1/sessions", headers=ha)
    assert sessions.status_code == 200
    items = sessions.json()["data"]["items"]
    assert len(items) == 2
    assert sum(1 for i in items if i["current"]) == 1
    other = next(i for i in items if not i["current"])
    assert other["device_summary"] == "Pixel 8"

    # 撤销设备 B 的会话：其访问令牌立即失效，设备 A 不受影响
    revoked = await client.delete(f"/v1/sessions/{other['session_id']}", headers=ha)
    assert revoked.status_code == 200
    me_b = await client.get("/v1/me", headers=hb)
    assert me_b.status_code == 401
    me_a = await client.get("/v1/me", headers=ha)
    assert me_a.status_code == 200

    # 不能撤销别人的会话（不可见）
    bob = await register_user(client, invites[1], "bob")
    stranger = await client.delete(f"/v1/sessions/{other['session_id']}",
                                   headers={"Authorization": f"Bearer {bob['token']}"})
    assert stranger.status_code == 404

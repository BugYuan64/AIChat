"""P4：AI 执行权限模式（permission_mode / workspace_dir）。

重点验证三件事：
1. 默认值是保守的 plan，不是 CLI 自身的 yolo；
2. 只有所有者能改，非所有者改不了；
3. 配置随 run.offer 下发到连接器，且重新配对不会丢失（存在 agent_profile 上）。
"""

import pytest

from tests.conftest import make_admin, register_user


def _h(user: dict) -> dict:
    return {"Authorization": f"Bearer {user['token']}"}


async def _create_agent(client, user, handle="cli-bot"):
    resp = await client.post(
        "/v1/agents",
        json={"handle": handle, "display_name": "CLI 助手"},
        headers=_h(user),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["account_id"]


@pytest.mark.asyncio
async def test_new_agent_defaults_to_plan_mode(client, ctx):
    """新 AI 的默认权限必须是 plan —— 不能继承 `zcode -p` 的 yolo。"""
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")
    agent_id = await _create_agent(client, alice)

    resp = await client.get(f"/v1/agents/{agent_id}", headers=_h(alice))
    assert resp.status_code == 200, resp.text
    policy = resp.json()["data"]["policy"]
    assert policy["permission_mode"] == "plan"
    assert policy["workspace_dir"] is None


@pytest.mark.asyncio
async def test_owner_can_set_policy(client, ctx):
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")
    agent_id = await _create_agent(client, alice)

    resp = await client.patch(
        f"/v1/agents/{agent_id}/policy",
        json={"permission_mode": "edit", "workspace_dir": "/srv/work"},
        headers=_h(alice),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["policy"]["permission_mode"] == "edit"
    assert body["policy"]["workspace_dir"] == "/srv/work"
    assert body["policy"]["policy_version"] >= 2


@pytest.mark.asyncio
async def test_non_owner_cannot_set_policy(client, ctx):
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")
    bob = await register_user(client, invites[1], "bob")
    agent_id = await _create_agent(client, alice)

    resp = await client.patch(
        f"/v1/agents/{agent_id}/policy",
        json={"permission_mode": "yolo"},
        headers=_h(bob),
    )
    assert resp.status_code == 403, resp.text

    # 确认没有被改动
    view = await client.get(f"/v1/agents/{agent_id}", headers=_h(alice))
    assert view.json()["data"]["policy"]["permission_mode"] == "plan"


@pytest.mark.asyncio
async def test_invalid_mode_rejected(client, ctx):
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")
    agent_id = await _create_agent(client, alice)

    resp = await client.patch(
        f"/v1/agents/{agent_id}/policy",
        json={"permission_mode": "root"},
        headers=_h(alice),
    )
    # 本项目校验错误统一用 400 VALIDATION_FAILED
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_policy_is_sent_in_run_offer(client, ctx):
    """权限模式必须随 run.offer 下发，否则适配器只能用自己的默认值。"""
    from aichat.modules.agents.models import RuntimeBinding
    from aichat.modules.runs.service import RunsService

    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")
    agent_id = await _create_agent(client, alice)

    # 设成 edit 并指定工作目录
    resp = await client.patch(
        f"/v1/agents/{agent_id}/policy",
        json={"permission_mode": "edit", "workspace_dir": "/srv/proj"},
        headers=_h(alice),
    )
    assert resp.status_code == 200, resp.text

    # 建一个 connector 绑定，触发 run
    async with ctx.db.session_factory() as session:
        connector_id = "conn-p4-test"
        session.add(RuntimeBinding(agent_account_id=agent_id, mode="connector",
                                   connector_id=connector_id, enabled=True, capabilities=[]))
        await session.commit()

    # claim_next 要求连接器在线；测试里直接放行
    from unittest.mock import patch

    with patch.object(ctx.hub, "connector_online", lambda cid: True):
        # 先建立联系人关系（自有 AI 也要走一次申请+代批）
        req = await client.post("/v1/contact-requests",
                                json={"target_account_id": agent_id}, headers=_h(alice))
        rid = req.json()["data"]["request_id"]
        await client.post(f"/v1/contact-requests/{rid}/decision",
                          json={"decision": "accept"}, headers=_h(alice))

        conv = await client.post("/v1/conversations/direct",
                                 json={"target_account_id": agent_id}, headers=_h(alice))
        conv_id = conv.json()["data"]["conversation_id"]
        send = await client.post(f"/v1/conversations/{conv_id}/messages",
                                 json={"client_message_id": "p4-offer-0001",
                                       "text": "开始工作"}, headers=_h(alice))
        # 首次发送返回 201（重放才是 200）
        assert send.status_code == 201, send.text
        assert send.json()["data"]["runs"], "应触发一个 run"

        async with ctx.db.session_factory() as session:
            runs = RunsService(ctx, session)
            claimed = await runs.claim_next(["connector"])
            assert claimed is not None, "应能领取到 run"
            run, attempt = claimed
            offer = await runs.build_offer(run, attempt)
            await session.commit()

    assert offer["execution_policy"]["permission_mode"] == "edit"
    assert offer["execution_policy"]["workspace_dir"] == "/srv/proj"

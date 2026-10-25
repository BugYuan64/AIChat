"""D4+D5 模型 API 通路：AI 账号 → 授权 → 私聊触发 → worker 执行（假模型流）→ 终态。"""

import pytest

from tests.conftest import make_admin, register_user


async def _seed_agent_with_binding(ctx, client, owner_headers, handle="code-assistant"):
    resp = await client.post("/v1/agents", json={
        "handle": handle, "display_name": "代码助手", "bio": "测试 AI",
    }, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    agent_id = resp.json()["data"]["account_id"]

    from aichat.core.ids import new_id
    from aichat.modules.agents.models import ProviderCredential, ProviderEndpoint, RuntimeBinding

    async with ctx.db.session_factory() as session:
        if await session.get(ProviderEndpoint, "fake") is None:
            session.add(ProviderEndpoint(code="fake", display_name="Fake Provider",
                                         base_url="https://api.fake.local/v1"))
        credential = ProviderCredential(
            id=new_id(), owner_account_id=owner_headers and "", provider_code="fake",
            ciphertext=ctx.cipher.encrypt("fake-key"),
        )
        # owner_account_id 仅记录归属，测试里用空串占位
        session.add(credential)
        await session.flush()
        session.add(RuntimeBinding(
            agent_account_id=agent_id, mode="model_api", provider_code="fake",
            credential_id=credential.id, model_name="fake-model", enabled=True,
        ))
        await session.commit()
    return agent_id


@pytest.mark.asyncio
async def test_model_run_lifecycle(client, ctx, monkeypatch):
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")
    ha = {"Authorization": f"Bearer {alice['token']}"}
    agent_id = await _seed_agent_with_binding(ctx, client, ha)

    # 申请联系人（AI 目标由所有者=alice 审批），同时建立使用授权
    req = await client.post("/v1/contact-requests", json={"target_account_id": agent_id}, headers=ha)
    request_id = req.json()["data"]["request_id"]
    decided = await client.post(f"/v1/contact-requests/{request_id}/decision",
                                json={"decision": "accept"}, headers=ha)
    assert decided.status_code == 200

    direct = await client.post("/v1/conversations/direct", json={"target_account_id": agent_id}, headers=ha)
    assert direct.status_code == 201
    conv_id = direct.json()["data"]["conversation_id"]

    send = await client.post(f"/v1/conversations/{conv_id}/messages", json={
        "client_message_id": "cccccccc-1111-1111-1111-111111111111", "text": "解释一下这段代码",
    }, headers=ha)
    assert send.status_code == 201
    runs = send.json()["data"]["runs"]
    assert len(runs) == 1 and runs[0]["state"] == "queued"
    run_id = runs[0]["run_id"]

    # 假模型：三个增量
    async def fake_stream(spec):
        for piece in ("你好", "，这是", "模型回复。"):
            yield piece

    from aichat.worker import executor

    monkeypatch.setattr(executor, "stream_chat", fake_stream)

    # 手动执行派发（测试中不跑后台循环）：先领取再执行
    from aichat.modules.runs.service import RunsService

    async with ctx.db.session_factory() as session:
        runs_service = RunsService(ctx, session)
        claimed = await runs_service.claim_next(["model_api"])
        assert claimed is not None
        assert claimed[0].id == run_id
        await session.commit()

    await executor.execute_model_run(ctx, run_id)

    # 验证终态：回复消息 final、run succeeded、事件可补拉
    history = await client.get(f"/v1/conversations/{conv_id}/messages", headers=ha)
    messages = history.json()["data"]["items"]
    ai_messages = [m for m in messages if m["sender_account_id"] == agent_id]
    assert len(ai_messages) == 1
    assert ai_messages[0]["status"] == "final"
    assert ai_messages[0]["text"] == "你好，这是模型回复。"
    assert ai_messages[0]["run_id"] == run_id

    run_view = await client.get(f"/v1/runs/{run_id}", headers=ha)
    assert run_view.status_code == 200
    assert run_view.json()["data"]["state"] == "succeeded"

    # 事件流：手动驱动扇出后，alice 能拉到 message.created / run.updated
    from aichat.modules.realtime.service import RealtimeService

    async with ctx.db.session_factory() as session:
        fanout = RealtimeService(ctx, session)
        while True:
            _, handled = await fanout.fanout_one()
            await session.commit()
            if not handled:
                break

    events = await client.get("/v1/events", params={"after": "0"}, headers=ha)
    assert events.status_code == 200
    types = [i["type"] for i in events.json()["data"]["items"]]
    assert "message.created" in types and "run.updated" in types
    cursor = events.json()["data"]["next_cursor"]
    assert int(cursor) > 0


@pytest.mark.asyncio
async def test_group_mention_triggers_only_target(client, ctx):
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")
    bob = await register_user(client, invites[1], "bob")
    ha = {"Authorization": f"Bearer {alice['token']}"}
    hb = {"Authorization": f"Bearer {bob['token']}"}

    agent_a = await _seed_agent_with_binding(ctx, client, ha, handle="agent-a")
    agent_b = await _seed_agent_with_binding(ctx, client, ha, handle="agent-b")

    for agent_id in (agent_a, agent_b):
        req = await client.post("/v1/contact-requests", json={"target_account_id": agent_id}, headers=ha)
        rid = req.json()["data"]["request_id"]
        await client.post(f"/v1/contact-requests/{rid}/decision", json={"decision": "accept"}, headers=ha)

    req = await client.post("/v1/contact-requests", json={"target_account_id": bob["account_id"]}, headers=ha)
    rid = req.json()["data"]["request_id"]
    await client.post(f"/v1/contact-requests/{rid}/decision", json={"decision": "accept"}, headers=hb)

    group = await client.post("/v1/groups", json={
        "title": "AI 群", "member_account_ids": [bob["account_id"], agent_a, agent_b],
    }, headers=ha)
    conv_id = group.json()["data"]["conversation_id"]
    for inv in group.json()["data"]["pending_invitations"]:
        await client.post(f"/v1/invitations/{inv['invitation_id']}/decision",
                          json={"decision": "accept"},
                          headers=hb if inv["target_account_id"] == bob["account_id"] else ha)

    # 只 @ agent_a：仅创建一个 run
    send = await client.post(f"/v1/conversations/{conv_id}/messages", json={
        "client_message_id": "dddddddd-1111-1111-1111-111111111111",
        "text": "@agent-a 帮我总结", "mentions": [agent_a],
    }, headers=ha)
    assert send.status_code == 201
    assert len(send.json()["data"]["runs"]) == 1
    assert send.json()["data"]["runs"][0]["agent_account_id"] == agent_a

    # 无 @ 不触发
    send2 = await client.post(f"/v1/conversations/{conv_id}/messages", json={
        "client_message_id": "dddddddd-2222-2222-2222-222222222222", "text": "普通消息",
    }, headers=ha)
    assert send2.status_code == 201
    assert send2.json()["data"]["runs"] == []

    # @ 非成员被拒
    bad = await client.post(f"/v1/conversations/{conv_id}/messages", json={
        "client_message_id": "dddddddd-3333-3333-3333-333333333333",
        "text": "@陌生人", "mentions": ["ffffffffffffffffffffffffffffffff"],
    }, headers=ha)
    assert bad.status_code == 400

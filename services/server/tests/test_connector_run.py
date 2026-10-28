"""连接器执行路径（服务层）：offer→ack→start→delta→complete + fencing/缺片拒绝。"""

import pytest

from tests.conftest import make_admin, register_user


async def _bind_connector(ctx, client, ha, agent_id: str) -> str:
    """完成配对并返回 connector_id。"""
    created = await client.post("/v1/pairings", json={
        "agent_id": agent_id, "connector_name": "runner-1", "platform": "linux",
        "adapter_kind": "echo",
    })
    data = created.json()["data"]
    await client.post(f"/v1/pairings/{data['pairing_id']}/decision", json={
        "decision": "approve", "confirm_code": data["confirm_code"], "expected_version": 1,
    }, headers=ha)
    await client.post("/v1/pairing-local-confirmation",
                      json={"device_code": data["device_code"], "confirmed": True})
    redeemed = await client.post("/v1/pairing-token", json={"device_code": data["device_code"]})
    return redeemed.json()["data"]["connector_id"]


@pytest.mark.asyncio
async def test_connector_run_full_path(client, ctx, monkeypatch):
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")
    ha = {"Authorization": f"Bearer {alice['token']}"}

    agent = await client.post("/v1/agents", json={
        "handle": "conn-ai", "display_name": "连接器助手"}, headers=ha)
    agent_id = agent.json()["data"]["account_id"]
    await _bind_connector(ctx, client, ha, agent_id)

    # 模拟连接器在线
    monkeypatch.setattr(ctx.hub, "connector_online", lambda cid: True)

    # 授权 + 私聊 + 触发
    req = await client.post("/v1/contact-requests", json={"target_account_id": agent_id}, headers=ha)
    rid = req.json()["data"]["request_id"]
    await client.post(f"/v1/contact-requests/{rid}/decision", json={"decision": "accept"}, headers=ha)
    direct = await client.post("/v1/conversations/direct", json={"target_account_id": agent_id}, headers=ha)
    conv_id = direct.json()["data"]["conversation_id"]
    send = await client.post(f"/v1/conversations/{conv_id}/messages", json={
        "client_message_id": "eeeeeeee-1111-1111-1111-111111111111", "text": "你好，请回复",
    }, headers=ha)
    run_id = send.json()["data"]["runs"][0]["run_id"]

    from aichat.core.errors import ApiError
    from aichat.modules.runs.models import Run
    from aichat.modules.runs.service import RunsService

    async with ctx.db.session_factory() as session:
        runs = RunsService(ctx, session)
        claimed = await runs.claim_next(["connector"])
        assert claimed is not None
        run, attempt = claimed
        assert run.id == run_id and attempt.mode == "connector"
        offer = await runs.build_offer(run, attempt)
        offer["context"] = [{"seq": i.seq, "text": i.text} for i in await runs.context_items(run.id)]
        assert any(c["seq"] == 1 for c in offer["context"])  # 上下文包含触发消息
        await session.commit()
        exec_id, attempt_no, fencing = attempt.execution_id, attempt.attempt_no, attempt.fencing_token

    async def frame(fn):
        async with ctx.db.session_factory() as session:
            runs = RunsService(ctx, session)
            result = await fn(runs)
            await session.commit()
            return result

    # ack → start（创建 draft 回复消息）
    await frame(lambda r: r.ack(run_id, exec_id, attempt_no, fencing))

    async def do_start(runs):
        _, _, message = await runs.start(run_id, exec_id, attempt_no, fencing)
        return message

    response_message = await frame(do_start)
    response_message_id = response_message.id
    assert response_message.status == "draft"

    # delta 0 → partial；delta 缺片 → DELTA_GAP
    await frame(lambda r: r.apply_delta(run_id, exec_id, attempt_no, fencing, 0, "你好"))
    with pytest.raises(ApiError) as gap:
        await frame(lambda r: r.apply_delta(run_id, exec_id, attempt_no, fencing, 2, "跳片"))
    assert gap.value.code == "DELTA_GAP"
    await frame(lambda r: r.apply_delta(run_id, exec_id, attempt_no, fencing, 1, "，世界"))

    # 旧 fencing → STALE_FENCE
    with pytest.raises(ApiError) as stale:
        await frame(lambda r: r.apply_delta(run_id, exec_id, attempt_no, fencing + 7, 2, "x"))
    assert stale.value.code == "STALE_FENCE"

    # 完成
    await frame(lambda r: r.complete(run_id, exec_id, attempt_no, fencing,
                                     final_text="你好，世界", content_hash=None,
                                     last_chunk_index=1, usage=None, finish_reason="stop"))

    history = await client.get(f"/v1/conversations/{conv_id}/messages", headers=ha)
    ai_messages = [m for m in history.json()["data"]["items"] if m["sender_account_id"] == agent_id]
    assert len(ai_messages) == 1
    assert ai_messages[0]["status"] == "final" and ai_messages[0]["text"] == "你好，世界"
    run_view = await client.get(f"/v1/runs/{run_id}", headers=ha)
    assert run_view.json()["data"]["state"] == "succeeded"

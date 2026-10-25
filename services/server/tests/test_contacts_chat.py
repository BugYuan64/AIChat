"""D2 联系人 + 私聊：申请审批、幂等建会话、幂等发送、伪造发送者拒绝。"""

import pytest

from tests.conftest import make_admin, register_user


@pytest.mark.asyncio
async def test_contact_and_direct_chat(client, ctx):
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")
    bob = await register_user(client, invites[1], "bob")
    ha = {"Authorization": f"Bearer {alice['token']}"}
    hb = {"Authorization": f"Bearer {bob['token']}"}

    # 精确查找
    found = await client.get("/v1/accounts/by-handle", params={"handle": "bob"}, headers=ha)
    assert found.status_code == 200
    bob_id = found.json()["data"]["account_id"]

    # 未成为联系人前不能建私聊
    early = await client.post("/v1/conversations/direct", json={"target_account_id": bob_id}, headers=ha)
    assert early.status_code == 403

    # 申请 → 对方接受
    req = await client.post("/v1/contact-requests", json={"target_account_id": bob_id}, headers=ha)
    assert req.status_code == 200
    request_id = req.json()["data"]["request_id"]
    pending = await client.get("/v1/contact-requests", headers=hb)
    assert any(i["request_id"] == request_id for i in pending.json()["data"]["items"])
    decided = await client.post(f"/v1/contact-requests/{request_id}/decision",
                                json={"decision": "accept"}, headers=hb)
    assert decided.status_code == 200

    # 幂等建私聊：201 → 200 同一 ID
    first = await client.post("/v1/conversations/direct", json={"target_account_id": bob_id}, headers=ha)
    assert first.status_code == 201
    conv_id = first.json()["data"]["conversation_id"]
    again = await client.post("/v1/conversations/direct", json={"target_account_id": bob_id}, headers=ha)
    assert again.status_code == 200
    assert again.json()["data"]["conversation_id"] == conv_id

    # 发消息：幂等重放 & 内容冲突
    send = await client.post(f"/v1/conversations/{conv_id}/messages", json={
        "client_message_id": "11111111-1111-1111-1111-111111111111", "text": "你好",
    }, headers=ha)
    assert send.status_code == 201
    message_id = send.json()["data"]["message"]["message_id"]
    seq1 = send.json()["data"]["message"]["seq"]

    replay = await client.post(f"/v1/conversations/{conv_id}/messages", json={
        "client_message_id": "11111111-1111-1111-1111-111111111111", "text": "你好",
    }, headers=ha)
    assert replay.status_code == 200
    assert replay.json()["data"]["message"]["message_id"] == message_id

    conflict = await client.post(f"/v1/conversations/{conv_id}/messages", json={
        "client_message_id": "11111111-1111-1111-1111-111111111111", "text": "改口",
    }, headers=ha)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    # 对方读取历史 + 已读
    history = await client.get(f"/v1/conversations/{conv_id}/messages", headers=hb)
    assert history.status_code == 200
    items = history.json()["data"]["items"]
    assert len(items) == 1 and items[0]["text"] == "你好"
    assert int(seq1) == 1

    read = await client.put(f"/v1/conversations/{conv_id}/read",
                            json={"through_seq": int(seq1)}, headers=hb)
    assert read.status_code == 200
    assert read.json()["data"]["unread"] == "0"

    # 陌生人不能读别人的会话
    carol = await register_user(client, invites[2], "carol")
    hc = {"Authorization": f"Bearer {carol['token']}"}
    stranger = await client.get(f"/v1/conversations/{conv_id}/messages", headers=hc)
    assert stranger.status_code == 403

    # 拉黑后发送被拒
    block = await client.post(f"/v1/contacts/{alice['account_id']}/block", headers=hb)
    assert block.status_code == 200
    blocked_send = await client.post(f"/v1/conversations/{conv_id}/messages", json={
        "client_message_id": "22222222-2222-2222-2222-222222222222", "text": "还在吗",
    }, headers=ha)
    assert blocked_send.status_code == 403

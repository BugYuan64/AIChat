"""D2 群聊：角色、邀请、成员区间可见性、退群后读取边界。"""

import pytest

from tests.conftest import make_admin, register_user


@pytest.mark.asyncio
async def test_group_membership_visibility(client, ctx):
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")
    bob = await register_user(client, invites[1], "bob")
    ha = {"Authorization": f"Bearer {alice['token']}"}
    hb = {"Authorization": f"Bearer {bob['token']}"}
    bob_id = bob["account_id"]

    req = await client.post("/v1/contact-requests", json={"target_account_id": bob_id}, headers=ha)
    request_id = req.json()["data"]["request_id"]
    await client.post(f"/v1/contact-requests/{request_id}/decision", json={"decision": "accept"}, headers=hb)

    group = await client.post("/v1/groups", json={"title": "项目组", "member_account_ids": [bob_id]}, headers=ha)
    assert group.status_code == 200
    conv_id = group.json()["data"]["conversation_id"]

    # 建群系统消息
    history_a = await client.get(f"/v1/conversations/{conv_id}/messages", headers=ha)
    assert history_a.status_code == 200
    assert any(i["kind"] == "system" for i in history_a.json()["data"]["items"])

    # bob 未接受邀请前看不到历史
    history_b = await client.get(f"/v1/conversations/{conv_id}/messages", headers=hb)
    assert history_b.status_code == 403

    invitations = group.json()["data"]["pending_invitations"]
    invitation_id = invitations[0]["invitation_id"]

    # 接受邀请：只看到加入系统消息及之后内容
    accepted = await client.post(f"/v1/invitations/{invitation_id}/decision",
                                 json={"decision": "accept"}, headers=hb)
    assert accepted.status_code == 200
    history_b = await client.get(f"/v1/conversations/{conv_id}/messages", headers=hb)
    assert history_b.status_code == 200
    items_b = history_b.json()["data"]["items"]
    visible_from = int(history_b.json()["data"]["visible_from_seq"])
    assert all(int(i["seq"]) >= visible_from for i in items_b)
    assert items_b and items_b[0]["kind"] == "system"

    # 群内互发
    send = await client.post(f"/v1/conversations/{conv_id}/messages", json={
        "client_message_id": "aaaaaaaa-1111-1111-1111-111111111111", "text": "开会了",
    }, headers=hb)
    assert send.status_code == 201

    # 移除 bob：之后不能再读
    detail = await client.get(f"/v1/conversations/{conv_id}", headers=ha)
    members = detail.json()["data"]["members"]
    bob_membership = next(m for m in members if m["account_id"] == bob_id)
    removed = await client.delete(
        f"/v1/conversations/{conv_id}/members/{bob_membership['membership_id']}", headers=ha)
    assert removed.status_code == 200

    after_remove = await client.get(f"/v1/conversations/{conv_id}/messages", headers=hb)
    assert after_remove.status_code == 403

    # 普通成员不能移除别人
    carol = await register_user(client, invites[2], "carol")
    hc = {"Authorization": f"Bearer {carol['token']}"}
    carol_id = carol["account_id"]
    req2 = await client.post("/v1/contact-requests", json={"target_account_id": carol_id}, headers=ha)
    rid2 = req2.json()["data"]["request_id"]
    await client.post(f"/v1/contact-requests/{rid2}/decision", json={"decision": "accept"}, headers=hc)
    inv2 = await client.post(f"/v1/conversations/{conv_id}/invitations",
                             json={"target_account_id": carol_id}, headers=ha)
    inv2_id = inv2.json()["data"]["invitation_id"]
    await client.post(f"/v1/invitations/{inv2_id}/decision", json={"decision": "accept"}, headers=hc)
    detail = await client.get(f"/v1/conversations/{conv_id}", headers=ha)
    alice_membership = next(m for m in detail.json()["data"]["members"] if m["account_id"] == alice["account_id"])
    forbidden = await client.delete(
        f"/v1/conversations/{conv_id}/members/{alice_membership['membership_id']}", headers=hc)
    assert forbidden.status_code == 403

    # 解散
    dissolved = await client.delete(f"/v1/conversations/{conv_id}", headers=ha)
    assert dissolved.status_code == 200

"""Request lists identify the counterpart and who can act on each request."""

from tests.conftest import make_admin, register_user


async def test_pending_requests_show_counterpart_and_direction(client, ctx):
    _, invites = await make_admin(ctx)
    alice = await register_user(client, invites[0], "alice")
    bob = await register_user(client, invites[1], "bob")
    ha = {"Authorization": f"Bearer {alice['token']}"}
    hb = {"Authorization": f"Bearer {bob['token']}"}
    response = await client.post("/v1/contact-requests", headers=ha,
                                 json={"target_account_id": bob["account_id"]})
    assert response.status_code == 200
    outgoing = (await client.get("/v1/contact-requests", headers=ha)).json()["data"]["items"][0]
    incoming = (await client.get("/v1/contact-requests", headers=hb)).json()["data"]["items"][0]
    assert outgoing["account"]["account_id"] == bob["account_id"]
    assert outgoing["direction"] == "outgoing"
    assert incoming["account"]["account_id"] == alice["account_id"]
    assert incoming["direction"] == "incoming"
    assert incoming["requester_account_id"] == alice["account_id"]
    assert incoming["target_account_id"] == bob["account_id"]


async def test_ai_owner_receives_incoming_request_with_target_ai(client, ctx):
    _, invites = await make_admin(ctx)
    owner = await register_user(client, invites[0], "owner")
    guest = await register_user(client, invites[1], "guest")
    ho = {"Authorization": f"Bearer {owner['token']}"}
    hg = {"Authorization": f"Bearer {guest['token']}"}
    agent = (await client.post("/v1/agents", headers=ho,
                              json={"handle": "helper-ai", "display_name": "AI"})).json()["data"]
    await client.post("/v1/contact-requests", headers=hg,
                      json={"target_account_id": agent["account_id"]})
    request = (await client.get("/v1/contact-requests", headers=ho)).json()["data"]["items"][0]
    assert request["direction"] == "incoming"
    assert request["target_account_id"] == agent["account_id"]
    assert request["account"]["account_id"] == guest["account_id"]

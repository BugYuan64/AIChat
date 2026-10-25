"""Two simultaneous redeemers may only receive one connector credential."""

import asyncio

from sqlalchemy import func, select

from aichat.core.errors import ApiError
from aichat.modules.pairing.models import Connector, PairingSession
from aichat.modules.pairing.service import PairingService
from tests.test_pairing import _setup_agent


async def test_pairing_redeem_has_one_winner_under_concurrency(client, ctx, monkeypatch):
    _, _, agent_id = await _setup_agent(client, ctx)
    created = (await client.post("/v1/pairings", json={
        "agent_id": agent_id, "connector_name": "race", "adapter_kind": "echo",
    })).json()["data"]
    async with ctx.db.session_factory() as session:
        pairing = await session.get(PairingSession, created["pairing_id"])
        pairing.status = "approved"
        await session.commit()

    original_lookup = PairingService._by_device_code
    both_read = asyncio.Event()
    readers = 0

    async def synchronized_lookup(service, code):
        nonlocal readers
        row = await original_lookup(service, code)
        readers += 1
        if readers == 2:
            both_read.set()
        await asyncio.wait_for(both_read.wait(), 5)
        return row

    monkeypatch.setattr(PairingService, "_by_device_code", synchronized_lookup)

    async def redeem():
        async with ctx.db.session_factory() as session:
            result = await PairingService(ctx, session).redeem_token(created["device_code"])
            await session.commit()
            return result

    results = await asyncio.wait_for(asyncio.gather(redeem(), redeem(), return_exceptions=True), 15)
    assert sum(isinstance(result, dict) for result in results) == 1, [type(result).__name__ for result in results]
    failures = [result for result in results if isinstance(result, ApiError)]
    assert len(failures) == 1, [type(result).__name__ for result in results]
    assert failures[0].status == 409
    assert failures[0].code == "PAIRING_CONSUMED"
    async with ctx.db.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Connector)) == 1

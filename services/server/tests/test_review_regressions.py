"""Regression coverage for defects found during deployment-readiness review."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect
from sqlalchemy import select

from aichat.core.errors import ApiError
from aichat.core.security import utcnow
from aichat.modules.agents.models import AgentGrant, AgentProfile, ProviderCredential, ProviderEndpoint, RuntimeBinding
from aichat.modules.conversations.models import Conversation, MembershipInterval
from aichat.modules.identity.models import Account, Invite, LoginSession
from aichat.modules.identity.service import IdentityService
from aichat.modules.messages.models import Message
from aichat.modules.messages.service import MessagesService
from aichat.modules.pairing.models import Connector
from aichat.modules.realtime.connector_gateway import _handle_run_frame, connector_ws
from aichat.modules.realtime.human_ws import realtime_ws
from aichat.modules.realtime.models import OutboxEvent
from aichat.modules.runs.models import Run, RunAttempt
from aichat.modules.runs.service import RunsService


async def seed_run(ctx, *, mode="connector", state="running"):
    async with ctx.db.session_factory() as session:
        session.add_all([
            Account(id="human", kind="human", handle="human", display_name="Human"),
            Account(id="agent", kind="ai", handle="agent", display_name="Agent"),
            Conversation(id="conversation", kind="direct", last_seq=2),
            MembershipInterval(id="member", conversation_id="conversation", account_id="human",
                               joined_seq=1, role="member"),
            Connector(id="connector", agent_account_id="agent", owner_account_id="human",
                      name="Test", platform="linux", adapter_kind="echo"),
            Message(id="trigger", conversation_id="conversation", seq=1, sender_account_id="human",
                    kind="text", text="hello"),
            Message(id="response", conversation_id="conversation", seq=2, sender_account_id="agent",
                    kind="text", text="", status="draft", run_id="run"),
            Run(id="run", conversation_id="conversation", trigger_message_id="trigger",
                agent_account_id="agent", requester_account_id="human", state=state,
                response_message_id="response", attempt_count=1, fencing_counter=1,
                deadline_at=utcnow() + timedelta(seconds=120),
                queue_deadline_at=utcnow() + timedelta(seconds=300)),
            RunAttempt(id="attempt", run_id="run", attempt_no=1, execution_id="execution",
                       mode=mode, connector_id="connector" if mode == "connector" else None,
                       fencing_token=1, state="running" if state != "dispatched" else "leased",
                       lease_until=utcnow() + timedelta(seconds=30)),
        ])
        await session.commit()


@pytest.mark.asyncio
async def test_history_reads_latest_page_before_older_page(ctx):
    await seed_run(ctx)
    async with ctx.db.session_factory() as session:
        session.add_all([Message(id=f"m{i}", conversation_id="conversation", seq=i,
                                sender_account_id="human", kind="text", text=str(i)) for i in (3, 4)])
        (await session.get(Conversation, "conversation")).last_seq = 4
        await session.commit()
    async with ctx.db.session_factory() as session:
        service = MessagesService(ctx, session)
        latest, _, more = await service.history("conversation", "human", None, 2)
        assert [m.seq for m in latest] == [3, 4]
        assert more
        older, _, more = await service.history("conversation", "human", 3, 2)
        assert [m.seq for m in older] == [1, 2]
        assert not more


class TicketSocket:
    def __init__(self, ctx, ticket):
        self.app = SimpleNamespace(state=SimpleNamespace(ctx=ctx))
        self.ticket = ticket
        self.frames = []

    async def accept(self):
        pass

    async def receive_json(self):
        if self.ticket:
            ticket, self.ticket = self.ticket, None
            return {"type": "ticket", "ticket": ticket}
        raise WebSocketDisconnect()

    async def send_json(self, frame):
        self.frames.append(frame)

    async def close(self, code=1000):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("audience,handler", [("human_events", realtime_ws), ("connector", connector_ws)])
async def test_websocket_ticket_cannot_be_replayed(ctx, audience, handler):
    await seed_run(ctx)
    async with ctx.db.session_factory() as session:
        session.add(LoginSession(id="login", account_id="human", refresh_hash="hash",
                                 expires_at=utcnow() + timedelta(days=1)))
        service = IdentityService(ctx, session)
        ticket = await service.create_ws_ticket("human" if audience == "human_events" else "connector",
                                                "human" if audience == "human_events" else "connector",
                                                audience, session_id="login")
        await session.commit()
    await handler(TicketSocket(ctx, ticket["ticket"]))
    async with ctx.db.session_factory() as session:
        with pytest.raises(ApiError):
            await IdentityService(ctx, session).consume_ws_ticket(ticket["ticket"], audience)


async def seed_model_run(ctx):
    await seed_run(ctx, mode="model_api", state="dispatched")
    async with ctx.db.session_factory() as session:
        await session.delete(await session.get(Message, "response"))
        run = await session.get(Run, "run")
        run.response_message_id = None
        (await session.get(Conversation, "conversation")).last_seq = 1
        session.add(ProviderEndpoint(code="fake", display_name="Fake", base_url="https://example.test/v1"))
        session.add(ProviderCredential(id="credential", owner_account_id="human", provider_code="fake",
                                       ciphertext=ctx.cipher.encrypt("test")))
        session.add(RuntimeBinding(agent_account_id="agent", mode="model_api", provider_code="fake",
                                   credential_id="credential", model_name="test", enabled=True))
        await session.commit()


@pytest.mark.asyncio
async def test_provider_error_persists_failed_run(ctx, monkeypatch):
    await seed_model_run(ctx)
    from aichat.worker import executor
    from aichat.runtime.base import ProviderError

    async def fail_stream(spec):
        raise ProviderError("provider_auth", "invalid key")
        yield "unreachable"

    monkeypatch.setattr(executor, "stream_chat", fail_stream)
    await executor.execute_model_run(ctx, "run")
    async with ctx.db.session_factory() as session:
        assert (await session.get(Run, "run")).state == "failed"
        assert (await session.get(RunAttempt, "attempt")).state == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("connector_id,revoked", [("other-connector", False), ("connector", True)])
async def test_connector_frame_requires_live_execution_owner(ctx, connector_id, revoked):
    await seed_run(ctx)
    async with ctx.db.session_factory() as session:
        if revoked:
            (await session.get(Connector, "connector")).revoked_at = utcnow()
            await session.commit()
        with pytest.raises(ApiError):
            await _handle_run_frame(ctx, session, RunsService(ctx, session), connector_id,
                                    {"type": "run.delta", "run_id": "run", "execution_id": "execution",
                                     "attempt_no": 1, "fencing_token": 1, "chunk_index": 0, "text": "bad"})


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["delta", "complete", "fail"])
async def test_terminal_run_cannot_be_rewritten_by_late_executor(ctx, operation):
    await seed_run(ctx, state="cancelled")
    async with ctx.db.session_factory() as session:
        service = RunsService(ctx, session)
        with pytest.raises(ApiError):
            if operation == "delta":
                await service.apply_delta("run", "execution", 1, 1, 0, "late")
            elif operation == "complete":
                await service.complete("run", "execution", 1, 1, "late", None, -1, None, "stop")
            else:
                await service.fail("run", "execution", 1, 1, "error", "late")


@pytest.mark.asyncio
async def test_message_events_are_complete_snapshots(ctx):
    await seed_run(ctx)
    async with ctx.db.session_factory() as session:
        service = MessagesService(ctx, session)
        message = await session.get(Message, "response")
        await service.emit_message_created(message, "conversation")
        await service.finalize_run_message(message, "done")
        await session.commit()
        events = list(await session.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at)))
        for event in events:
            assert event.payload["conversation_id"] == "conversation"
            assert event.payload["run_id"] == "run"
            assert event.payload["seq"] == "2"
            assert event.payload["created_at"].endswith("Z")
            assert event.payload["sender_account_id"] == "agent"


@pytest.mark.asyncio
async def test_expired_dispatch_lease_invalidates_attempt_before_requeue(ctx):
    await seed_run(ctx, state="dispatched")
    async with ctx.db.session_factory() as session:
        (await session.get(RunAttempt, "attempt")).lease_until = utcnow() - timedelta(seconds=1)
        await session.commit()
    async with ctx.db.session_factory() as session:
        service = RunsService(ctx, session)
        assert await service.expire_stale_runs() == 1
        await session.commit()
        assert (await session.get(Run, "run")).state == "queued"
        assert (await session.get(RunAttempt, "attempt")).state == "expired"
        assert await service.current_attempt("run") is None


@pytest.mark.asyncio
async def test_concurrent_registrations_consume_invite_once(ctx):
    async with ctx.db.session_factory() as session:
        session.add(Invite(code="single-use", expires_at=utcnow() + timedelta(days=1)))
        await session.commit()

    async def register(handle):
        async with ctx.db.session_factory() as session:
            try:
                account = await IdentityService(ctx, session).register("single-use", handle, handle,
                                                                        "test-password-123")
                await session.commit()
                return account.id
            except ApiError as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(register("first"), register("second"))
    assert sum(isinstance(result, str) for result in results) == 1
    assert sum(isinstance(result, ApiError) and result.code == "VALIDATION_FAILED" for result in results) == 1


@pytest.mark.asyncio
async def test_concurrent_refresh_tokens_rotate_once(ctx):
    from aichat.core.security import sha256_hex

    await seed_run(ctx)
    async with ctx.db.session_factory() as session:
        session.add(LoginSession(id="login", account_id="human", refresh_hash=sha256_hex("refresh"),
                                 expires_at=utcnow() + timedelta(days=1)))
        await session.commit()

    async def refresh():
        async with ctx.db.session_factory() as session:
            try:
                result = await IdentityService(ctx, session).refresh("refresh")
                await session.commit()
                return result
            except ApiError as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(refresh(), refresh())
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, ApiError) and result.code == "AUTH_INVALID" for result in results) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["logout", "refresh"])
async def test_logout_and_refresh_disconnect_old_session(ctx, operation):
    from aichat.core.security import sha256_hex
    from aichat.modules.realtime.hub import HumanConnection

    await seed_run(ctx)
    async with ctx.db.session_factory() as session:
        session.add(LoginSession(id="login", account_id="human", refresh_hash=sha256_hex("refresh"),
                                 expires_at=utcnow() + timedelta(days=1)))
        await session.commit()

    conn = HumanConnection("human", drain=None, session_id="login")
    await ctx.hub.add_human(conn)
    async with ctx.db.session_factory() as session:
        service = IdentityService(ctx, session)
        if operation == "logout":
            await service.logout("human", "login")
        else:
            await service.refresh("refresh")
        await session.commit()
    assert not conn.alive


@pytest.mark.asyncio
async def test_grant_does_not_reveal_runs_from_unrelated_conversations(ctx):
    await seed_run(ctx)
    async with ctx.db.session_factory() as session:
        session.add(Account(id="stranger", kind="human", handle="stranger", display_name="Stranger"))
        session.add(AgentGrant(id="grant", agent_account_id="agent", human_account_id="stranger"))
        session.add(AgentProfile(account_id="agent", owner_account_id="owner"))
        await session.commit()
    async with ctx.db.session_factory() as session:
        service = RunsService(ctx, session)
        with pytest.raises(ApiError) as exc:
            await service.get_run_for_human("run", "stranger")
        assert exc.value.code == "FORBIDDEN"
        assert (await service.get_run_for_human("run", "owner")).id == "run"


@pytest.mark.asyncio
async def test_model_cancel_drops_pending_buffer_without_changing_to_failed(ctx, monkeypatch):
    await seed_model_run(ctx)
    from aichat.worker import executor

    async def cancelled_stream(spec):
        yield "buffered"
        async with ctx.db.session_factory() as session:
            await RunsService(ctx, session).request_cancel("run")
            await session.commit()
        yield "late"

    monkeypatch.setattr(executor, "stream_chat", cancelled_stream)
    await executor.execute_model_run(ctx, "run")
    async with ctx.db.session_factory() as session:
        assert (await session.get(Run, "run")).state == "cancelled"


@pytest.mark.asyncio
async def test_connector_gap_error_identifies_execution_and_resume_index(ctx):
    await seed_run(ctx)
    async with ctx.db.session_factory() as session:
        ticket = await IdentityService(ctx, session).create_ws_ticket("connector", "connector", "connector")
        await session.commit()

    class GapSocket(TicketSocket):
        def __init__(self, ctx, ticket):
            super().__init__(ctx, ticket)
            self.gap_sent = False

        async def receive_json(self):
            if self.ticket:
                return await super().receive_json()
            if not self.gap_sent:
                self.gap_sent = True
                return {"type": "run.delta", "run_id": "run", "execution_id": "execution",
                        "attempt_no": 1, "fencing_token": 1, "chunk_index": 3, "text": "missing"}
            raise WebSocketDisconnect()

    socket = GapSocket(ctx, ticket["ticket"])
    await connector_ws(socket)
    error = next(frame for frame in socket.frames if frame["type"] == "error")
    assert error["code"] == "DELTA_GAP"
    assert error["execution_id"] == "execution"
    assert error["next_chunk_index"] == 0


@pytest.mark.asyncio
async def test_login_and_refresh_include_account_snapshot(client, ctx):
    from aichat.core.security import hash_password
    from aichat.modules.identity.models import HumanCredential

    await seed_run(ctx)
    async with ctx.db.session_factory() as session:
        session.add(HumanCredential(account_id="human", password_hash=hash_password("test-password-123")))
        await session.commit()
    login = await client.post("/v1/auth/login", json={"handle": "human", "password": "test-password-123"})
    assert login.status_code == 200
    data = login.json()["data"]
    expected = {"account_id": "human", "kind": "human", "handle": "human", "display_name": "Human",
                "avatar_url": None, "bio": None, "status": "active"}
    assert data["account"] == expected
    refresh = await client.post("/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert refresh.status_code == 200
    assert refresh.json()["data"]["account"] == expected


@pytest.mark.asyncio
async def test_retry_rejects_revoked_requester_grant(ctx):
    await seed_run(ctx, state="failed")
    async with ctx.db.session_factory() as session:
        session.add(AgentGrant(id="revoked", agent_account_id="agent", human_account_id="human",
                               revoked_at=utcnow()))
        await session.commit()
    async with ctx.db.session_factory() as session:
        with pytest.raises(ApiError) as exc:
            await RunsService(ctx, session).retry("run", "human")
        assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_running_connector_lease_expires_before_global_deadline(ctx):
    await seed_run(ctx)
    async with ctx.db.session_factory() as session:
        (await session.get(RunAttempt, "attempt")).lease_until = utcnow() - timedelta(seconds=1)
        await session.commit()
    async with ctx.db.session_factory() as session:
        assert await RunsService(ctx, session).expire_stale_runs() == 1
        await session.commit()
        assert (await session.get(Run, "run")).state == "recovery_required"
        assert (await session.get(RunAttempt, "attempt")).state == "expired"


@pytest.mark.asyncio
async def test_model_executor_renews_lease_while_waiting_for_output(ctx, monkeypatch):
    await seed_model_run(ctx)
    ctx.settings.run_lease_seconds = 1
    ctx.settings.run_lease_renew_seconds = 0.05
    async with ctx.db.session_factory() as session:
        attempt = await session.get(RunAttempt, "attempt")
        initial_lease = utcnow() + timedelta(seconds=1)
        attempt.lease_until = initial_lease
        await session.commit()
    from aichat.worker import executor

    async def slow_stream(spec):
        await asyncio.sleep(0.15)
        async with ctx.db.session_factory() as session:
            attempt = await session.get(RunAttempt, "attempt")
            assert attempt.lease_until > initial_lease
        yield "done"

    monkeypatch.setattr(executor, "stream_chat", slow_stream)
    await executor.execute_model_run(ctx, "run")
    async with ctx.db.session_factory() as session:
        assert (await session.get(Run, "run")).state == "succeeded"


@pytest.mark.asyncio
async def test_late_cancellation_cannot_erase_unknown_execution_outcome(ctx):
    await seed_run(ctx, state="recovery_required")
    async with ctx.db.session_factory() as session:
        (await session.get(RunAttempt, "attempt")).state = "expired"
        await session.commit()
    async with ctx.db.session_factory() as session:
        await RunsService(ctx, session).confirm_cancelled("execution", "none")
        await session.commit()
        assert (await session.get(Run, "run")).state == "recovery_required"


@pytest.mark.asyncio
async def test_model_lease_loss_is_not_reported_as_user_cancellation(ctx, monkeypatch):
    await seed_model_run(ctx)
    ctx.settings.run_lease_renew_seconds = 0.01
    from aichat.worker import executor

    async def failed_renewal(service, attempt):
        raise RuntimeError("test lease storage unavailable")

    async def slow_stream(spec):
        await asyncio.sleep(0.08)
        yield "late output"

    monkeypatch.setattr(RunsService, "renew_lease", failed_renewal)
    monkeypatch.setattr(executor, "stream_chat", slow_stream)
    await executor.execute_model_run(ctx, "run")
    async with ctx.db.session_factory() as session:
        # No terminal outcome is known; the maintenance lease expiry owns recovery.
        assert (await session.get(Run, "run")).state == "running"


@pytest.mark.asyncio
async def test_ready_connector_is_offline_after_socket_disconnect(ctx):
    await seed_run(ctx)
    async with ctx.db.session_factory() as session:
        ticket = await IdentityService(ctx, session).create_ws_ticket("connector", "connector", "connector")
        await session.commit()

    class ReadySocket(TicketSocket):
        sent_ready = False

        async def receive_json(self):
            if self.ticket:
                return await super().receive_json()
            if not self.sent_ready:
                self.sent_ready = True
                return {"type": "connector.ready"}
            raise WebSocketDisconnect()

    await connector_ws(ReadySocket(ctx, ticket["ticket"]))
    async with ctx.db.session_factory() as session:
        assert (await session.get(Connector, "connector")).status == "offline"

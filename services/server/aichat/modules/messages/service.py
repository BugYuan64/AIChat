"""消息模块：持久化消息、幂等发送、AI 触发判定、AI 回复消息生命周期、已读游标。

写入规则（contracts/PROTOCOL.md §4）：短事务内锁会话分配 seq，消息+Run+outbox 同事务提交；
作者身份由登录会话推导；幂等键为 conversation+sender+client_message_id。
"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.context import AppContext
from aichat.core.errors import forbidden, idempotency_conflict, membership_revoked, not_found, validation_failed
from aichat.core.ids import new_id
from aichat.core.outbox import emit
from aichat.core.security import utcnow
from aichat.modules.agents.models import AgentGrant, AgentProfile, RuntimeBinding
from aichat.modules.conversations.models import Conversation, DirectPair, MembershipInterval
from aichat.modules.contacts.models import Contact
from aichat.modules.contacts.service import ContactsService
from aichat.modules.identity.models import Account
from aichat.modules.messages.models import Message, ReadCursor
from aichat.modules.messages.schemas import message_out


def _content_fingerprint(text: str, mentions: list[str], reply_to: str | None) -> str:
    return json.dumps([text, sorted(mentions), reply_to], ensure_ascii=False)


class MessagesService:
    def __init__(self, ctx: AppContext, session: AsyncSession) -> None:
        self.ctx = ctx
        self.settings = ctx.settings
        self.session = session

    # ---- 查询辅助 ----

    async def get_conversation(self, conversation_id: str, *, lock: bool = False) -> Conversation:
        query = select(Conversation).where(Conversation.id == conversation_id)
        if lock and self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        conv = await self.session.scalar(query)
        if conv is None:
            raise not_found("会话不存在")
        return conv

    async def active_membership(self, conversation_id: str, account_id: str) -> MembershipInterval | None:
        return await self.session.scalar(
            select(MembershipInterval).where(
                MembershipInterval.conversation_id == conversation_id,
                MembershipInterval.account_id == account_id,
                MembershipInterval.left_at.is_(None),
            )
        )

    async def visible_interval(self, conversation_id: str, account_id: str) -> MembershipInterval | None:
        return await self.session.scalar(
            select(MembershipInterval)
            .where(
                MembershipInterval.conversation_id == conversation_id,
                MembershipInterval.account_id == account_id,
            )
            .order_by(MembershipInterval.joined_seq.desc())
            .limit(1)
        )

    async def member_account_ids(self, conversation_id: str) -> list[str]:
        rows = await self.session.scalars(
            select(MembershipInterval.account_id).where(
                MembershipInterval.conversation_id == conversation_id,
                MembershipInterval.left_at.is_(None),
            )
        )
        return list(rows)

    async def get_message(self, message_id: str) -> Message:
        message = await self.session.get(Message, message_id)
        if message is None:
            raise not_found("消息不存在")
        return message

    # ---- 低层写入（供本模块与 runs 模块共用；调用方负责事务与权限） ----

    async def _insert_message(
        self,
        conv: Conversation,
        *,
        sender_account_id: str | None,
        kind: str,
        text: str,
        mentions: list[str] | None = None,
        client_message_id: str | None = None,
        reply_to_message_id: str | None = None,
        run_id: str | None = None,
        trigger_message_id: str | None = None,
        status: str = "final",
    ) -> Message:
        conv.last_seq += 1
        message = Message(
            id=new_id(),
            conversation_id=conv.id,
            seq=conv.last_seq,
            sender_account_id=sender_account_id,
            kind=kind,
            text=text,
            mentions=mentions or [],
            client_message_id=client_message_id,
            reply_to_message_id=reply_to_message_id,
            run_id=run_id,
            trigger_message_id=trigger_message_id,
            status=status,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def emit_message_created(self, message: Message, conversation_id: str) -> None:
        await self.session.flush()
        sender = await self.session.get(Account, message.sender_account_id) if message.sender_account_id else None
        await emit(
            self.session,
            "message.created",
            message_out(message, sender),
            conversation_id=conversation_id,
        )

    async def emit_message_updated(self, message: Message, conversation_id: str) -> None:
        await self.session.flush()
        sender = await self.session.get(Account, message.sender_account_id) if message.sender_account_id else None
        await emit(
            self.session,
            "message.updated",
            message_out(message, sender),
            conversation_id=conversation_id,
        )

    async def create_system_message(self, conv: Conversation, text: str) -> Message:
        message = await self._insert_message(conv, sender_account_id=None, kind="system", text=text)
        await self.emit_message_created(message, conv.id)
        return message

    # ---- 人类发送 ----

    async def send_human_message(
        self,
        conversation_id: str,
        sender_account_id: str,
        client_message_id: str,
        text: str,
        mentions: list[str],
        reply_to_message_id: str | None,
    ) -> tuple[Message, list, bool]:
        """返回 (message, runs, replayed)。replayed=True 表示幂等重放。"""
        conv = await self.get_conversation(conversation_id, lock=True)
        if conv.status != "active":
            raise forbidden("会话已关闭")
        membership = await self.active_membership(conversation_id, sender_account_id)
        if membership is None:
            raise membership_revoked()

        existing = await self.session.scalar(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.sender_account_id == sender_account_id,
                Message.client_message_id == client_message_id,
            )
        )
        if existing is not None:
            if existing.client_message_id == client_message_id:
                fingerprint = _content_fingerprint(existing.text, existing.mentions or [], existing.reply_to_message_id)
                if fingerprint != _content_fingerprint(text, mentions, reply_to_message_id):
                    raise idempotency_conflict()
                from aichat.modules.runs.models import Run

                runs = list(await self.session.scalars(
                    select(Run).where(Run.trigger_message_id == existing.id)
                ))
                return existing, runs, True

        members = await self.member_account_ids(conversation_id)
        if sender_account_id not in members:
            raise membership_revoked()

        mentions = sorted(set(mentions))
        for target in mentions:
            if target not in members:
                raise validation_failed("mentions 必须是当前成员账号")

        if reply_to_message_id is not None:
            reply = await self.get_message(reply_to_message_id)
            if reply.conversation_id != conversation_id:
                raise validation_failed("引用消息必须属于同一会话")

        # 私聊：联系人/拉黑/授权检查（联系人移除后阻止新发送，历史保留）
        if conv.kind == "direct":
            pair = await self.session.get(DirectPair, conversation_id)
            other_id = pair.high_id if pair.low_id == sender_account_id else pair.low_id
            contacts = ContactsService(self.ctx, self.session)
            if await contacts.is_blocked(sender_account_id, other_id):
                raise forbidden("无法在该私聊中发送消息")
            if not await contacts.is_contact(sender_account_id, other_id):
                raise forbidden("双方不再是联系人，无法发送新消息")

        message = await self._insert_message(
            conv,
            sender_account_id=sender_account_id,
            kind="text",
            text=text,
            mentions=mentions,
            client_message_id=client_message_id,
            reply_to_message_id=reply_to_message_id,
        )
        await self.emit_message_created(message, conversation_id)

        # 触发判定：私聊人类→AI 自动触发；群聊显式 @AI（≤3）
        targets: list[str] = []
        if conv.kind == "direct":
            pair = await self.session.get(DirectPair, conversation_id)
            other_id = pair.high_id if pair.low_id == sender_account_id else pair.low_id
            other = await self.session.get(Account, other_id)
            if other is not None and other.kind == "ai":
                targets = [other_id]
        else:
            ai_targets = []
            for target in mentions:
                account = await self.session.get(Account, target)
                if account is not None and account.kind == "ai":
                    ai_targets.append(target)
            if len(ai_targets) > self.settings.max_mentions_per_message:
                raise validation_failed(f"单条消息最多 @ {self.settings.max_mentions_per_message} 个 AI")
            targets = ai_targets

        runs = []
        if targets:
            from aichat.modules.runs.service import RunsService  # 延迟导入避免环

            runs_service = RunsService(self.ctx, self.session)
            for agent_id in targets:
                run = await runs_service.create_for_trigger(conv, message, agent_id, sender_account_id)
                if run is not None:
                    runs.append(run)
        return message, runs, False

    # ---- AI 回复消息生命周期（由 runs 模块驱动） ----

    async def create_run_response_message(self, conv: Conversation, run, agent_account_id: str) -> Message:
        message = await self._insert_message(
            conv,
            sender_account_id=agent_account_id,
            kind="text",
            text="",
            run_id=run.id,
            trigger_message_id=run.trigger_message_id,
            status="draft",
        )
        await self.emit_message_created(message, conv.id)
        return message

    async def append_run_delta(self, message: Message, chunk_index: int, text: str, *, force_event: bool) -> None:
        message.text = (message.text or "") + text
        message.status = "partial"
        message.revision += 1
        message.last_chunk_index = chunk_index
        if force_event:
            await self.emit_message_updated(message, message.conversation_id)

    async def finalize_run_message(self, message: Message, final_text: str) -> None:
        message.text = final_text
        message.status = "final"
        message.revision += 1
        await self.emit_message_updated(message, message.conversation_id)

    async def mark_run_message_terminal(self, message: Message, reason: str) -> None:
        if message.status != "final":
            message.status = "final" if not message.text else "partial"
            message.terminal_reason = reason
            message.revision += 1
            await self.emit_message_updated(message, message.conversation_id)

    # ---- 历史与已读 ----

    async def history(
        self,
        conversation_id: str,
        account_id: str,
        before_seq: int | None,
        limit: int,
    ) -> tuple[list[Message], int, bool]:
        """要求当前活跃成员身份；区间 [joined_seq, left_seq] 约束可见范围。"""
        interval = await self.active_membership(conversation_id, account_id)
        if interval is None:
            raise membership_revoked()
        conv = await self.get_conversation(conversation_id)
        upper = interval.left_seq if interval.left_seq is not None else conv.last_seq
        if before_seq is not None:
            upper = min(upper, before_seq - 1)
        query = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.seq >= interval.joined_seq,
                Message.seq <= upper,
            )
            .order_by(Message.seq.desc())
            .limit(limit + 1)
        )
        rows = list(await self.session.scalars(query))
        has_more = len(rows) > limit
        rows = rows[:limit]
        rows.reverse()
        return rows, interval.joined_seq, has_more

    async def set_read_cursor(self, conversation_id: str, account_id: str, through_seq: int) -> dict:
        interval = await self.active_membership(conversation_id, account_id)
        if interval is None:
            raise membership_revoked()
        conv = await self.get_conversation(conversation_id)
        upper = min(conv.last_seq, interval.left_seq if interval.left_seq is not None else conv.last_seq)
        if through_seq > upper:
            raise validation_failed("已读位置不能超过当前可见范围")
        cursor = await self.session.get(ReadCursor, (conversation_id, account_id))
        if cursor is None:
            self.session.add(ReadCursor(conversation_id=conversation_id, account_id=account_id,
                                        read_seq=through_seq))
            read_seq = through_seq
        else:
            cursor.read_seq = max(cursor.read_seq, through_seq)
            read_seq = cursor.read_seq
        return {"read_seq": str(read_seq), "unread": str(max(0, conv.last_seq - read_seq))}

    # ---- 授权检查（供 runs 复用） ----

    async def has_active_grant(self, agent_account_id: str, human_account_id: str) -> bool:
        grant = await self.session.scalar(
            select(AgentGrant).where(
                AgentGrant.agent_account_id == agent_account_id,
                AgentGrant.human_account_id == human_account_id,
                AgentGrant.revoked_at.is_(None),
            )
        )
        if grant is not None:
            return True
        profile = await self.session.get(AgentProfile, agent_account_id)
        return profile is not None and profile.owner_account_id == human_account_id

    async def enabled_binding(self, agent_account_id: str) -> RuntimeBinding | None:
        binding = await self.session.get(RuntimeBinding, agent_account_id)
        if binding is None or not binding.enabled:
            return None
        return binding

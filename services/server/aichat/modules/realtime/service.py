"""realtime 服务：outbox 扇出 → per-account inbox；事件补拉与可见性过滤。"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.context import AppContext
from aichat.core.errors import cursor_expired
from aichat.core.security import utcnow
from aichat.modules.conversations.models import MembershipInterval
from aichat.modules.realtime.models import EventStream, InboxEvent, OutboxEvent

MESSAGE_EVENTS = {"message.created", "message.updated"}


class RealtimeService:
    def __init__(self, ctx: AppContext, session: AsyncSession) -> None:
        self.ctx = ctx
        self.settings = ctx.settings
        self.session = session

    # ---- 扇出 ----

    async def fanout_one(self) -> tuple[list[str], bool]:
        """处理最早的一个未扇出事件；返回（被通知账号, 是否有处理）。"""
        row = await self.session.scalar(
            select(OutboxEvent).where(OutboxEvent.fanned_out.is_(False))
            .order_by(OutboxEvent.created_at.asc()).limit(1)
        )
        if row is None:
            return [], False
        # PG 下锁定该行，防两个扇出进程交错；SQLite 单写者天然串行
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            locked = await self.session.scalar(
                select(OutboxEvent).where(OutboxEvent.id == row.id).with_for_update()
            )
            if locked is None or locked.fanned_out:
                return [], True
            row = locked
        if row.fanned_out:
            return [], True

        recipients: set[str] = set(row.subject_account_ids or [])
        if row.conversation_id:
            members = await self.session.scalars(
                select(MembershipInterval.account_id).where(
                    MembershipInterval.conversation_id == row.conversation_id,
                    MembershipInterval.left_at.is_(None),
                )
            )
            recipients.update(members)
            # 离开成员的墓碑：membership.changed 的主体账号始终投递
            subject = (row.payload or {}).get("subject_account_id")
            if subject:
                recipients.add(subject)

        retention = timedelta(days=self.settings.event_retention_days)
        for account_id in sorted(recipients):
            stream = await self.session.get(EventStream, account_id)
            if stream is None:
                stream = EventStream(account_id=account_id, last_cursor=0)
                self.session.add(stream)
                await self.session.flush()
            stream.last_cursor += 1
            self.session.add(InboxEvent(
                account_id=account_id, cursor=stream.last_cursor, event_id=row.id,
                expires_at=utcnow() + retention,
            ))
        row.fanned_out = True
        return list(recipients), True

    # ---- 补拉 ----

    async def events_page(self, account_id: str, after: int, limit: int) -> dict:
        limit = max(1, min(limit, 500))
        earliest = await self.session.scalar(
            select(InboxEvent.cursor).where(InboxEvent.account_id == account_id)
            .order_by(InboxEvent.cursor.asc()).limit(1)
        )
        stream = await self.session.get(EventStream, account_id)
        if stream is not None and earliest is not None and after < earliest - 1:
            raise cursor_expired()
        if stream is not None and earliest is None and after < stream.last_cursor:
            # 没有任何保留事件但游标落后 → 全部过期
            raise cursor_expired()

        result = await self.session.execute(
            select(InboxEvent, OutboxEvent)
            .join(OutboxEvent, OutboxEvent.id == InboxEvent.event_id)
            .where(InboxEvent.account_id == account_id, InboxEvent.cursor > after)
            .order_by(InboxEvent.cursor.asc())
            .limit(limit)
        )
        rows = result.all()
        items = []
        next_cursor = after
        for inbox, outbox in rows:
            next_cursor = max(next_cursor, inbox.cursor)
            if not await self._visible(account_id, outbox):
                continue  # 撤权内容：跳过但允许 cursor 前进
            items.append(self._event_frame(inbox, outbox))
        has_more = next_cursor < (stream.last_cursor if stream else 0)
        return {"items": items, "next_cursor": str(next_cursor), "has_more": has_more}

    async def _visible(self, account_id: str, event: OutboxEvent) -> bool:
        if event.conversation_id is None:
            return True
        payload = event.payload or {}
        subject = payload.get("subject_account_id")
        if subject == account_id:
            return True
        interval = await self.session.scalar(
            select(MembershipInterval)
            .where(MembershipInterval.conversation_id == event.conversation_id,
                   MembershipInterval.account_id == account_id)
            .order_by(MembershipInterval.joined_seq.desc()).limit(1)
        )
        if interval is None:
            return False
        if interval.left_at is not None:
            seq = int(payload["seq"]) if payload.get("seq") is not None else None
            if seq is None:
                return False  # 离开后只保留自身主体事件
            if seq > interval.left_seq:
                return False
        return payload.get("seq") is None or int(payload["seq"]) >= interval.joined_seq or event.type not in MESSAGE_EVENTS

    def _event_frame(self, inbox: InboxEvent, outbox: OutboxEvent) -> dict:
        payload = dict(outbox.payload or {})
        frame = {
            "protocol_version": 1,
            "type": outbox.type,
            "event_id": outbox.id,
            "cursor": str(inbox.cursor),
            "payload": payload,
            "occurred_at": outbox.occurred_at.isoformat() + "Z",
        }
        if outbox.conversation_id:
            frame["conversation_id"] = outbox.conversation_id
            if "seq" in payload:
                frame["seq"] = str(payload["seq"])
        return frame

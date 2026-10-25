from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aichat.core.db import Base
from aichat.core.security import utcnow


class OutboxEvent(Base):
    """事务性待发布事件：与业务写入同事务提交，由分发器扇出。"""

    __tablename__ = "outbox_event"
    __table_args__ = (Index("ix_outbox_pending", "fanned_out", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(32))
    subject_account_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    fanned_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class EventStream(Base):
    """每账号一行，锁内分配单调 cursor。"""

    __tablename__ = "event_stream"

    account_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class InboxEvent(Base):
    """每账号的持久事件投递：PK(account_id, cursor)，UNIQUE(account_id, event_id) 幂等。"""

    __tablename__ = "inbox_event"
    __table_args__ = (
        UniqueConstraint("account_id", "event_id", name="uq_inbox_account_event"),
        Index("ix_inbox_expiry", "account_id", "expires_at"),
    )

    account_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    cursor: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

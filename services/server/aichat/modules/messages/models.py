from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aichat.core.db import Base
from aichat.core.security import utcnow

MessageKind = Enum("text", "system", name="message_kind")
MessageStatus = Enum("draft", "partial", "final", name="message_status")


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_message_conv_seq"),
        # 人类消息幂等键：同会话同发送者同 client_message_id（非人类消息该列为 NULL，不参与唯一约束）
        Index(
            "uq_message_client_id",
            "conversation_id",
            "sender_account_id",
            "client_message_id",
            unique=True,
        ),
        Index("ix_message_conv_seq", "conversation_id", "seq"),
        # AI 回复消息：一个 run 至多一条回复消息
        Index("uq_message_run", "run_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(32), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    sender_account_id: Mapped[str | None] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(MessageKind, nullable=False, default="text")
    text: Mapped[str] = mapped_column(String(262144), nullable=False, default="")
    client_message_id: Mapped[str | None] = mapped_column(String(64))
    mentions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reply_to_message_id: Mapped[str | None] = mapped_column(String(32))
    run_id: Mapped[str | None] = mapped_column(String(32))
    trigger_message_id: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(MessageStatus, nullable=False, default="final")
    terminal_reason: Mapped[str | None] = mapped_column(String(16))  # cancel/error/unknown
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class ReadCursor(Base):
    """人类账号/会话已读游标：只前进且不超过可见上限。"""

    __tablename__ = "read_cursor"

    conversation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    read_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

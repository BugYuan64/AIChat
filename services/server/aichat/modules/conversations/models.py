from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aichat.core.db import Base
from aichat.core.security import utcnow

ConversationKind = Enum("direct", "group", name="conversation_kind")
ConversationStatus = Enum("active", "closed", name="conversation_status")
MemberRole = Enum("member", "admin", "owner", name="member_role")
InvitationStatus = Enum("pending", "accepted", "rejected", "expired", "revoked", name="invitation_status")


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(ConversationKind, nullable=False)
    title: Mapped[str | None] = mapped_column(String(128))
    owner_account_id: Mapped[str | None] = mapped_column(String(32))  # 仅 group
    status: Mapped[str] = mapped_column(ConversationStatus, nullable=False, default="active")
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    permission_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class DirectPair(Base):
    """规范化（low<high）双人键，保证同对账号唯一私聊。"""

    __tablename__ = "direct_pair"
    __table_args__ = (UniqueConstraint("low_id", "high_id", name="uq_direct_pair"),)

    conversation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    low_id: Mapped[str] = mapped_column(String(32), nullable=False)
    high_id: Mapped[str] = mapped_column(String(32), nullable=False)


class MembershipInterval(Base):
    """一次成员区间：joined_seq/left_seq 决定历史可见性；重新入群产生新行。"""

    __tablename__ = "membership_interval"
    __table_args__ = (
        Index("ix_membership_conv_account_left", "conversation_id", "account_id", "left_seq"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(32), nullable=False)
    account_id: Mapped[str] = mapped_column(String(32), nullable=False)
    role: Mapped[str] = mapped_column(MemberRole, nullable=False, default="member")
    joined_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    left_seq: Mapped[int | None] = mapped_column(Integer)
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    left_at: Mapped[datetime | None] = mapped_column(DateTime)


class GroupInvitation(Base):
    __tablename__ = "group_invitation"
    __table_args__ = (
        Index("ix_invitation_pending", "conversation_id", "target_account_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_account_id: Mapped[str] = mapped_column(String(32), nullable=False)
    inviter_id: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(InvitationStatus, nullable=False, default="pending")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

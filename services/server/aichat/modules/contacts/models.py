from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aichat.core.db import Base
from aichat.core.security import utcnow

RequestStatus = Enum("pending", "accepted", "rejected", "cancelled", name="contact_request_status")


class ContactRequest(Base):
    __tablename__ = "contact_request"
    __table_args__ = (
        Index("ix_contact_request_pair", "requester_id", "target_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    requester_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(RequestStatus, nullable=False, default="pending")
    note: Mapped[str | None] = mapped_column(String(256))
    decided_by: Mapped[str | None] = mapped_column(String(32))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Contact(Base):
    """无序账号对唯一联系人关系。"""

    __tablename__ = "contact"
    __table_args__ = (UniqueConstraint("low_id", "high_id", name="uq_contact_pair"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    low_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    high_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Block(Base):
    """方向性拉黑：blocker 拒绝与 blocked 的一切私聊与邀请。"""

    __tablename__ = "block"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    blocker_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    blocked_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

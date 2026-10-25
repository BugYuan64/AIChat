from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from aichat.core.db import Base
from aichat.core.security import utcnow

AccountKind = Enum("human", "ai", name="account_kind")
AccountStatus = Enum("active", "disabled", name="account_status")


class Account(Base):
    __tablename__ = "account"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(AccountKind, nullable=False)
    handle: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    bio: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(AccountStatus, nullable=False, default="active")
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class HumanCredential(Base):
    __tablename__ = "human_credential"

    account_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class LoginSession(Base):
    __tablename__ = "login_session"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    refresh_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    device_summary: Mapped[str | None] = mapped_column(String(256))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Invite(Base):
    __tablename__ = "invite"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_by: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(String(256))
    used_by: Mapped[str | None] = mapped_column(String(32))
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class WsTicket(Base):
    """一次性 WSS 握手票据，只存哈希。人类票据绑定签发时的登录会话，撤销会话即断开连接。"""

    __tablename__ = "ws_ticket"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)  # human | connector
    subject_id: Mapped[str] = mapped_column(String(32), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(32))  # 仅 subject_type=human 时填写
    audience: Mapped[str] = mapped_column(String(32), nullable=False)  # human_events | connector
    ticket_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

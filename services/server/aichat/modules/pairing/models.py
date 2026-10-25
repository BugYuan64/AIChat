from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from aichat.core.db import Base
from aichat.core.security import utcnow

PairingStatus = Enum(
    "pending_user", "pending_local", "approved", "redeemed",
    "denied", "expired", "cancelled",
    name="pairing_status",
)
ConnectorStatus = Enum("pending", "offline", "online", "ready", "degraded", "revoked", name="connector_status")


class PairingSession(Base):
    """配对会话：pending_user → pending_local → approved → redeemed；非终态可转 denied/expired/cancelled。
    device_code 与 short_code 只存哈希；confirm_code 供两端人工核对，配对过期即失效。"""

    __tablename__ = "pairing_session"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    agent_account_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    connector_name: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    adapter_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="echo")
    requested_capabilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    short_code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    confirm_code: Mapped[str] = mapped_column(String(16), nullable=False)
    device_code_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(PairingStatus, nullable=False, default="pending_user")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    decided_by: Mapped[str | None] = mapped_column(String(32))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    local_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Connector(Base):
    """已绑定的外部连接器。refresh_credential 只存哈希；撤销立即拒绝。"""

    __tablename__ = "connector"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    agent_account_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    owner_account_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    adapter_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="echo")
    capabilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    refresh_hash: Mapped[str | None] = mapped_column(String(128), unique=True)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    binding_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(ConnectorStatus, nullable=False, default="offline")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

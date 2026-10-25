from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from aichat.core.db import Base
from aichat.core.security import utcnow


class AuditEvent(Base):
    """脱敏审计：不记录密钥、完整 prompt 或工具日志。"""

    __tablename__ = "audit_event"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    actor_account_id: Mapped[str | None] = mapped_column(String(32), index=True)
    actor_connector_id: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)

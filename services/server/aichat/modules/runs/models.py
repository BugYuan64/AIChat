from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Index, Integer, String, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aichat.core.db import Base
from aichat.core.security import utcnow

RunState = Enum(
    "queued", "dispatched", "running", "cancel_requested",
    "succeeded", "failed", "cancelled", "expired", "recovery_required",
    name="run_state",
)
AttemptState = Enum("leased", "running", "succeeded", "failed", "cancelled", "expired", name="attempt_state")


class Run(Base):
    """一次 AI 任务。自动触发（is_auto）的 Run 按 触发消息+AI 唯一；显式重试不占该约束。"""

    __tablename__ = "run"
    __table_args__ = (
        Index("uq_run_auto_trigger", "trigger_message_id", "agent_account_id", unique=True,
              sqlite_where=text("is_auto = 1"), postgresql_where=text("is_auto")),
        Index("ix_run_queue", "state", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trigger_message_id: Mapped[str] = mapped_column(String(32), nullable=False)
    agent_account_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    requester_account_id: Mapped[str] = mapped_column(String(32), nullable=False)
    response_message_id: Mapped[str | None] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(RunState, nullable=False, default="queued")
    is_auto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retried_from_run_id: Mapped[str | None] = mapped_column(String(32))
    binding_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    permission_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fencing_counter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deadline_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    queue_deadline_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class RunAttempt(Base):
    """一次领取执行：execution_id 幂等；fencing_token 拒绝旧领取者的迟到写入。"""

    __tablename__ = "run_attempt"
    __table_args__ = (
        UniqueConstraint("run_id", "attempt_no", name="uq_attempt_no"),
        Index("ix_attempt_lease", "state", "lease_until"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # model_api | connector
    connector_id: Mapped[str | None] = mapped_column(String(32))
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(AttemptState, nullable=False, default="leased")
    lease_until: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    last_chunk_hash: Mapped[str | None] = mapped_column(String(128))
    pending_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class RunContextItem(Base):
    """运行上下文快照：创建时固定，不随后续消息变化。"""

    __tablename__ = "run_context_item"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(String(32), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    sender_account_id: Mapped[str | None] = mapped_column(String(32))
    sender_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="human")
    text: Mapped[str] = mapped_column(String(262144), nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

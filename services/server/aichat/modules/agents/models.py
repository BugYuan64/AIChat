from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aichat.core.db import Base
from aichat.core.security import utcnow

BindingMode = Enum("model_api", "connector", name="binding_mode")


class AgentProfile(Base):
    """AI 账号档案：account_id 指向 kind=ai 的 Account，owner 是人类账号。"""

    __tablename__ = "agent_profile"

    account_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_account_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="granted")
    system_prompt: Mapped[str | None] = mapped_column(String(16384))
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AgentGrant(Base):
    """AI 使用授权：所有者自动持有；其他人类须显式授权才能触发该 AI。"""

    __tablename__ = "agent_grant"
    __table_args__ = (UniqueConstraint("agent_account_id", "human_account_id", name="uq_agent_grant"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    agent_account_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    human_account_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)


class ProviderEndpoint(Base):
    """管理员维护的模型供应商白名单端点。"""

    __tablename__ = "provider_endpoint"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False, default="openai_chat")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ProviderCredential(Base):
    """模型凭据密文；主密钥独立于数据库保存。"""

    __tablename__ = "provider_credential"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_account_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_code: Mapped[str] = mapped_column(String(32), nullable=False)
    ciphertext: Mapped[str] = mapped_column(String(4096), nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class RuntimeBinding(Base):
    """每 AI 仅一条绑定行（主键保证）；generation 递增使旧任务/旧连接器失效。"""

    __tablename__ = "runtime_binding"

    agent_account_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    mode: Mapped[str] = mapped_column(BindingMode, nullable=False)
    provider_code: Mapped[str | None] = mapped_column(String(32))
    credential_id: Mapped[str | None] = mapped_column(String(32))
    model_name: Mapped[str | None] = mapped_column(String(128))
    system_prompt: Mapped[str | None] = mapped_column(String(16384))
    connector_id: Mapped[str | None] = mapped_column(String(32))
    capabilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    test_ok_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """集中配置。生产环境全部经环境变量注入，不落仓库。"""

    model_config = SettingsConfigDict(env_prefix="AICHAT_", env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite+aiosqlite:///./aichat.db"
    public_base_url: str = ""
    cors_origins: list[str] = Field(default_factory=list)

    # 认证
    jwt_secret: str = "dev-only-secret-change-me"
    access_token_seconds: int = 15 * 60
    refresh_token_days: int = 30
    ws_ticket_seconds: int = 30

    # 模型凭据加密主密钥（Fernet key，urlsafe base64）；缺省时由 jwt_secret 派生（仅限开发）
    credential_master_key: str = ""

    # 配对
    pairing_ttl_seconds: int = 5 * 60
    pairing_poll_seconds: int = 5
    short_code_alphabet: str = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    short_code_length: int = 8
    confirm_code_length: int = 6
    connector_access_token_seconds: int = 15 * 60
    connector_refresh_days: int = 7

    # 运行
    run_lease_seconds: int = 30
    run_lease_renew_seconds: int = 10
    run_dispatch_ack_seconds: int = 10
    # CLI agent（zcode/codex/hermes）单次任务常需数分钟，120 秒会把正常任务误判为超时
    run_deadline_seconds: int = 1800
    run_queue_deadline_seconds: int = 60 * 60
    run_max_attempts: int = 3
    max_context_messages: int = 30
    max_human_active_runs: int = 2
    max_agent_queued_runs: int = 20
    max_mentions_per_message: int = 3

    # 消息与事件
    human_message_max_bytes: int = 16 * 1024
    ai_message_max_bytes: int = 256 * 1024
    final_text_inline_max_bytes: int = 32 * 1024
    event_retention_days: int = 7
    delta_checkpoint_min_interval_ms: int = 1000
    delta_checkpoint_pending_bytes: int = 4 * 1024

    # 实时
    heartbeat_seconds: int = 20
    offline_after_seconds: int = 60
    ws_first_frame_seconds: int = 10
    model_http_timeout_seconds: int = 90

    # 限流（进程内滑动窗口，v1 单实例）
    rate_limit_login_per_min: int = 10
    rate_limit_pairing_per_min: int = 5
    rate_limit_send_per_min: int = 60

    # 事件推送循环
    fanout_poll_seconds: float = 0.3
    run_loop_seconds: float = 0.5

    @model_validator(mode="after")
    def require_production_secrets(self):
        if self.is_prod:
            if len(self.jwt_secret.encode("utf-8")) < 32:
                raise ValueError("Production AICHAT_JWT_SECRET must contain at least 32 bytes")
            if not self.credential_master_key:
                raise ValueError("Production AICHAT_CREDENTIAL_MASTER_KEY is required")
            try:
                Fernet(self.credential_master_key.encode("ascii"))
            except (ValueError, UnicodeError) as exc:
                raise ValueError("AICHAT_CREDENTIAL_MASTER_KEY must be a valid Fernet key") from exc
        return self

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()

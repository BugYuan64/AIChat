from pydantic import BaseModel, Field


class AgentCreateIn(BaseModel):
    handle: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    bio: str | None = Field(default=None, max_length=2048)


class AgentPatchIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    bio: str | None = Field(default=None, max_length=2048)
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")


class AgentPolicyIn(BaseModel):
    """CLI agent 的执行权限配置。

    permission_mode 必须显式选择：`zcode -p` 自身默认 yolo（全自动批准），
    平台不能把这个默认值静默继承给用户。
    """

    permission_mode: str = Field(pattern=r"^(plan|edit|build|yolo|guarded)$")
    workspace_dir: str | None = Field(default=None, max_length=512)


class ModelBindingIn(BaseModel):
    provider_code: str
    credential: str = Field(min_length=8, max_length=4096)  # 模型 API 密钥，仅本次请求出现
    model_name: str = Field(min_length=1, max_length=128)
    system_prompt: str | None = Field(default=None, max_length=16384)
    test: bool = True  # 连接测试通过才启用


class GrantIn(BaseModel):
    human_account_id: str


class ProviderEndpointIn(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    display_name: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=8, max_length=512)
    protocol: str = Field(default="openai_chat", pattern=r"^openai_chat$")
    enabled: bool = True


def agent_out(account, profile, binding=None, connector=None) -> dict:
    return {
        "account_id": account.id,
        "kind": "ai",
        "handle": account.handle,
        "display_name": account.display_name,
        "bio": account.bio,
        "status": account.status,
        "owner_account_id": profile.owner_account_id if profile else None,
        "policy": (
            {
                "permission_mode": profile.permission_mode,
                "workspace_dir": profile.workspace_dir,
            }
            if profile is not None
            else None
        ),
        "binding": (
            {
                "mode": binding.mode,
                "provider_code": binding.provider_code,
                "model_name": binding.model_name,
                "generation": str(binding.generation),
                "enabled": binding.enabled,
                "test_ok_at": binding.test_ok_at.isoformat() + "Z" if binding.test_ok_at else None,
            }
            if binding is not None
            else None
        ),
        "connector": (
            {
                "connector_id": connector.id,
                "name": connector.name,
                "platform": connector.platform,
                "status": connector.status,
                "last_seen_at": connector.last_seen_at.isoformat() + "Z" if connector.last_seen_at else None,
            }
            if connector is not None
            else None
        ),
    }


def grant_out(grant, account) -> dict:
    return {
        "grant_id": grant.id,
        "human_account_id": grant.human_account_id,
        "handle": account.handle if account else None,
        "display_name": account.display_name if account else None,
        "revoked_at": grant.revoked_at.isoformat() + "Z" if grant.revoked_at else None,
    }

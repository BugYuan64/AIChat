from pydantic import BaseModel, Field


class PairingCreateIn(BaseModel):
    agent_id: str
    connector_name: str = Field(min_length=1, max_length=128)
    platform: str = Field(default="unknown", max_length=64)
    adapter_kind: str = Field(default="echo", max_length=64)
    requested_capabilities: list[str] = Field(default_factory=lambda: ["chat.text", "output.stream", "run.cancel", "run.query"])


class PairingDecisionIn(BaseModel):
    decision: str = Field(pattern=r"^(approve|deny)$")
    confirm_code: str
    expected_version: int = Field(ge=1)


class DeviceCodeIn(BaseModel):
    device_code: str = Field(min_length=16)


class LocalConfirmIn(BaseModel):
    device_code: str = Field(min_length=16)
    confirmed: bool = True


class RefreshCredentialIn(BaseModel):
    refresh_credential: str = Field(min_length=16)


class RevokeIn(BaseModel):
    reason: str | None = Field(default=None, max_length=256)


def pairing_public_out(pairing, agent_account=None, owner_account=None) -> dict:
    out = {
        "pairing_id": pairing.id,
        "agent_id": pairing.agent_account_id,
        "connector_name": pairing.connector_name,
        "platform": pairing.platform,
        "adapter_kind": pairing.adapter_kind,
        "requested_capabilities": pairing.requested_capabilities or [],
        "confirm_code": pairing.confirm_code,
        "status": pairing.status,
        "version": str(pairing.version),
        "expires_at": pairing.expires_at.isoformat() + "Z",
    }
    if agent_account is not None:
        out["agent_display_name"] = agent_account.display_name
        out["agent_handle"] = agent_account.handle
    if owner_account is not None:
        out["owner_display_name"] = owner_account.display_name
    return out

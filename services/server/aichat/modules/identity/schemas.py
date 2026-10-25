from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    invite_code: str
    handle: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)


class LoginIn(BaseModel):
    handle: str
    password: str
    device_summary: str | None = Field(default=None, max_length=256)


class RefreshIn(BaseModel):
    refresh_token: str


class TicketIn(BaseModel):
    audience: str = Field(pattern=r"^(human_events|connector)$")


class InviteIn(BaseModel):
    note: str | None = Field(default=None, max_length=256)
    expires_days: int = Field(default=7, ge=1, le=365)
    count: int = Field(default=1, ge=1, le=50)


def account_out(account) -> dict:
    return {
        "account_id": account.id,
        "kind": account.kind,
        "handle": account.handle,
        "display_name": account.display_name,
        "avatar_url": account.avatar_url,
        "bio": account.bio,
        "status": account.status,
    }


def invite_out(invite) -> dict:
    return {
        "code": invite.code,
        "note": invite.note,
        "used": invite.used_by is not None,
        "expires_at": invite.expires_at.isoformat() + "Z" if invite.expires_at else None,
    }

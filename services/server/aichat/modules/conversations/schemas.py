from pydantic import BaseModel, Field


class DirectIn(BaseModel):
    target_account_id: str
    client_request_id: str | None = None


class GroupIn(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    member_account_ids: list[str] = Field(default_factory=list, max_length=200)


class InviteIn(BaseModel):
    target_account_id: str


class InvitationDecisionIn(BaseModel):
    decision: str = Field(pattern=r"^(accept|reject)$")


def membership_out(m) -> dict:
    return {
        "membership_id": m.id,
        "conversation_id": m.conversation_id,
        "account_id": m.account_id,
        "role": m.role,
        "joined_seq": str(m.joined_seq),
        "left_seq": str(m.left_seq) if m.left_seq is not None else None,
    }


def invitation_out(inv) -> dict:
    return {
        "invitation_id": inv.id,
        "conversation_id": inv.conversation_id,
        "target_account_id": inv.target_account_id,
        "inviter_id": inv.inviter_id,
        "status": inv.status,
        "created_at": inv.created_at.isoformat() + "Z",
    }


def conversation_out(conv) -> dict:
    return {
        "conversation_id": conv.id,
        "kind": conv.kind,
        "title": conv.title,
        "status": conv.status,
        "permission_version": str(conv.permission_version),
        "last_seq": str(conv.last_seq),
        "created_at": conv.created_at.isoformat() + "Z",
    }

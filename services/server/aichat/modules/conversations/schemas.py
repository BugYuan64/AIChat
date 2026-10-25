from pydantic import BaseModel, Field


class DirectIn(BaseModel):
    target_account_id: str
    client_request_id: str | None = None


class GroupIn(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    member_account_ids: list[str] = Field(default_factory=list, max_length=200)


class InviteIn(BaseModel):
    """兼容两种形式：单个 target_account_id 或批量 invitee_account_ids。"""

    target_account_id: str | None = None
    invitee_account_ids: list[str] = Field(default_factory=list, max_length=100)

    def target_ids(self) -> list[str]:
        ids = [self.target_account_id] if self.target_account_id else []
        ids.extend(i for i in self.invitee_account_ids if i not in ids)
        if not ids:
            raise ValueError("缺少被邀请账号")
        return ids


class InvitationDecisionIn(BaseModel):
    decision: str = Field(pattern=r"^(accept|reject)$")


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=128)


class RoleIn(BaseModel):
    role: str = Field(pattern=r"^(owner|admin|member)$")


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

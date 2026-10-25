from pydantic import BaseModel, Field


class ContactRequestIn(BaseModel):
    target_account_id: str


class DecisionIn(BaseModel):
    decision: str = Field(pattern=r"^(accept|reject)$")


class BlockIn(BaseModel):
    pass


def contact_request_out(request_row, account, viewer_account_id: str) -> dict:
    return {
        "request_id": request_row.id,
        "status": request_row.status,
        "requester_account_id": request_row.requester_id,
        "target_account_id": request_row.target_id,
        "direction": "outgoing" if request_row.requester_id == viewer_account_id else "incoming",
        "account": public_account_out(account),
        "created_at": request_row.created_at.isoformat() + "Z",
    }


def public_account_out(account) -> dict:
    return {
        "account_id": account.id,
        "kind": account.kind,
        "handle": account.handle,
        "display_name": account.display_name,
        "avatar_url": account.avatar_url,
        "bio": account.bio,
    }

from pydantic import BaseModel, Field


class MessageIn(BaseModel):
    client_message_id: str = Field(min_length=8, max_length=64)
    text: str = Field(min_length=1, max_length=16384)
    mentions: list[str] = Field(default_factory=list, max_length=20)
    reply_to_message_id: str | None = None


class ReadIn(BaseModel):
    through_seq: int = Field(ge=0)


def message_out(message, sender=None) -> dict:
    return {
        "message_id": message.id,
        "conversation_id": message.conversation_id,
        "seq": str(message.seq),
        "sender_account_id": message.sender_account_id,
        "sender": (
            {
                "account_id": sender.id,
                "kind": sender.kind,
                "handle": sender.handle,
                "display_name": sender.display_name,
            }
            if sender is not None
            else None
        ),
        "kind": message.kind,
        "text": message.text,
        "mentions": message.mentions or [],
        "client_message_id": message.client_message_id,
        "reply_to_message_id": message.reply_to_message_id,
        "run_id": message.run_id,
        "trigger_message_id": message.trigger_message_id,
        "status": message.status,
        "terminal_reason": message.terminal_reason,
        "revision": str(message.revision),
        "created_at": message.created_at.isoformat() + "Z",
        "updated_at": message.updated_at.isoformat() + "Z",
    }

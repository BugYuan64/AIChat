"""跨模块异步集成：事务内写 outbox，分发器扇出为 per-account inbox 事件。
模块之间不直接推送，一律经此通道（见 contracts/PROTOCOL.md §9）。"""

from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.ids import new_id
from aichat.core.security import utcnow
from aichat.modules.realtime.models import OutboxEvent

# 持久事件类型全集；临时事件（run.delta/typing/presence）不进 outbox
PERSISTENT_EVENT_TYPES = frozenset(
    {"message.created", "message.updated", "membership.changed", "conversation.closed", "run.updated", "binding.changed"}
)


async def emit(
    session: AsyncSession,
    type: str,
    payload: dict,
    *,
    conversation_id: str | None = None,
    subject_account_ids: list[str] | None = None,
) -> str:
    if type not in PERSISTENT_EVENT_TYPES:
        raise ValueError(f"未知持久事件类型: {type}")
    event_id = new_id()
    session.add(
        OutboxEvent(
            id=event_id,
            type=type,
            conversation_id=conversation_id,
            subject_account_ids=subject_account_ids or [],
            payload=payload,
            occurred_at=utcnow(),
        )
    )
    return event_id

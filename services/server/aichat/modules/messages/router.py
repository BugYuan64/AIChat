from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.db import get_session
from aichat.core.deps import AuthHuman, current_human
from aichat.modules.identity.models import Account
from aichat.modules.messages.schemas import MessageIn, ReadIn, message_out
from aichat.modules.messages.service import MessagesService
from aichat.modules.runs.service import RunsService

router = APIRouter(tags=["messages"])


def svc(request: Request, session: AsyncSession = Depends(get_session)) -> MessagesService:
    return MessagesService(request.app.state.ctx, session)


@router.post("/conversations/{conversation_id}/messages")
async def send(conversation_id: str, body: MessageIn, auth: AuthHuman = Depends(current_human),
               service: MessagesService = Depends(svc)):
    message, runs, replayed = await service.send_human_message(
        conversation_id, auth.account_id, body.client_message_id, body.text,
        body.mentions, body.reply_to_message_id,
    )
    sender = await service.session.get(Account, auth.account_id)
    runs_service = RunsService(service.ctx, service.session)
    payload = {
        "message": message_out(message, sender),
        "runs": [runs_service.run_out(r) for r in runs],
    }
    return JSONResponse(status_code=200 if replayed else 201, content=payload)


@router.get("/conversations/{conversation_id}/messages")
async def history(conversation_id: str, before_seq: int | None = None, limit: int = 50,
                  auth: AuthHuman = Depends(current_human), service: MessagesService = Depends(svc)):
    limit = max(1, min(limit, 100))
    rows, visible_from, has_more = await service.history(conversation_id, auth.account_id, before_seq, limit)
    senders: dict[str, Account] = {}
    for row in rows:
        if row.sender_account_id and row.sender_account_id not in senders:
            senders[row.sender_account_id] = await service.session.get(Account, row.sender_account_id)
    items = [message_out(m, senders.get(m.sender_account_id or "")) for m in rows]
    return {
        "items": items,
        "has_more": has_more,
        "visible_from_seq": str(visible_from),
        "next_before_seq": str(rows[0].seq) if rows else None,
    }


@router.put("/conversations/{conversation_id}/read")
async def set_read(conversation_id: str, body: ReadIn, auth: AuthHuman = Depends(current_human),
                   service: MessagesService = Depends(svc)):
    return await service.set_read_cursor(conversation_id, auth.account_id, body.through_seq)

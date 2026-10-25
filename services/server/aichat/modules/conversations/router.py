from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.db import get_session
from aichat.core.deps import AuthHuman, current_human
from aichat.modules.conversations.models import GroupInvitation
from aichat.modules.conversations.schemas import (
    DirectIn,
    GroupIn,
    InvitationDecisionIn,
    InviteIn,
    conversation_out,
    invitation_out,
)
from aichat.modules.conversations.service import ConversationsService
from aichat.modules.identity.models import Account

router = APIRouter(tags=["conversations"])


def svc(request: Request, session: AsyncSession = Depends(get_session)) -> ConversationsService:
    return ConversationsService(request.app.state.ctx, session)


@router.post("/conversations/direct")
async def create_direct(body: DirectIn, auth: AuthHuman = Depends(current_human),
                        service: ConversationsService = Depends(svc)):
    conv, created = await service.create_direct(auth.account_id, body.target_account_id)
    detail = await service.conversation_detail(conv.id, auth.account_id)
    return JSONResponse(status_code=201 if created else 200, content=detail)


@router.post("/groups")
async def create_group(body: GroupIn, auth: AuthHuman = Depends(current_human),
                       service: ConversationsService = Depends(svc)):
    conv, invitations = await service.create_group(auth.account_id, body.title, body.member_account_ids)
    detail = await service.conversation_detail(conv.id, auth.account_id)
    detail["pending_invitations"] = [invitation_out(i) for i in invitations]
    return detail


@router.get("/conversations")
async def list_conversations(auth: AuthHuman = Depends(current_human),
                             service: ConversationsService = Depends(svc)):
    return {"items": await service.list_for_account(auth.account_id)}


@router.get("/conversations/{conversation_id}")
async def conversation_detail(conversation_id: str, auth: AuthHuman = Depends(current_human),
                              service: ConversationsService = Depends(svc)):
    return await service.conversation_detail(conversation_id, auth.account_id)


@router.post("/conversations/{conversation_id}/invitations")
async def invite(conversation_id: str, body: InviteIn, auth: AuthHuman = Depends(current_human),
                 service: ConversationsService = Depends(svc)):
    invitation = await service.invite(conversation_id, auth.account_id, body.target_account_id)
    return invitation_out(invitation)


@router.get("/conversations/{conversation_id}/invitations")
async def list_invitations(conversation_id: str, auth: AuthHuman = Depends(current_human),
                           service: ConversationsService = Depends(svc)):
    membership = await service.messages.active_membership(conversation_id, auth.account_id)
    if membership is None or membership.role not in ("owner", "admin"):
        from aichat.core.errors import forbidden

        raise forbidden("只有群主或管理员可以查看邀请")
    rows = list(await service.session.scalars(
        select(GroupInvitation).where(
            GroupInvitation.conversation_id == conversation_id,
            GroupInvitation.status == "pending",
        )
    ))
    return {"items": [invitation_out(i) for i in rows]}


@router.post("/invitations/{invitation_id}/decision")
async def decide_invitation(invitation_id: str, body: InvitationDecisionIn,
                            auth: AuthHuman = Depends(current_human),
                            service: ConversationsService = Depends(svc)):
    invitation = await service.decide_invitation(invitation_id, auth.account_id, body.decision == "accept")
    return invitation_out(invitation)


@router.delete("/conversations/{conversation_id}/members/{membership_id}")
async def remove_member(conversation_id: str, membership_id: str, auth: AuthHuman = Depends(current_human),
                        service: ConversationsService = Depends(svc)):
    membership = await service.remove_member(conversation_id, auth.account_id, membership_id)
    return {"membership_id": membership.id, "left_seq": str(membership.left_seq)}


@router.delete("/conversations/{conversation_id}")
async def dissolve(conversation_id: str, auth: AuthHuman = Depends(current_human),
                   service: ConversationsService = Depends(svc)):
    conv = await service.dissolve(conversation_id, auth.account_id)
    return conversation_out(conv)

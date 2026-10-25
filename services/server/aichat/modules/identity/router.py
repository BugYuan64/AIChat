from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.context import AppContext
from aichat.core.db import get_session
from aichat.core.deps import AuthHuman, current_human, get_ctx, require_admin
from aichat.core.errors import not_found
from aichat.modules.identity.schemas import (
    InviteIn,
    LoginIn,
    ProfilePatchIn,
    RefreshIn,
    RegisterIn,
    TicketIn,
    account_out,
    invite_out,
)
from aichat.modules.identity.service import IdentityService

router = APIRouter(tags=["identity"])


def svc(request: Request, session: AsyncSession = Depends(get_session)) -> IdentityService:
    return IdentityService(request.app.state.ctx, session)


@router.post("/auth/register")
async def register(body: RegisterIn, request: Request, service: IdentityService = Depends(svc)):
    account = await service.register(body.invite_code, body.handle, body.display_name, body.password)
    return account_out(account)


@router.post("/auth/login")
async def login(body: LoginIn, request: Request, service: IdentityService = Depends(svc)):
    client_ip = request.client.host if request.client else ""
    return await service.login(body.handle, body.password, body.device_summary, client_ip=client_ip)


@router.post("/auth/refresh")
async def refresh(body: RefreshIn, request: Request, service: IdentityService = Depends(svc)):
    return await service.refresh(body.refresh_token)


@router.post("/auth/logout")
async def logout(request: Request, auth: AuthHuman = Depends(current_human),
                 service: IdentityService = Depends(svc)):
    await service.logout(auth.account_id, auth.session_id)
    return {"revoked": True}


@router.get("/me")
async def me(auth: AuthHuman = Depends(current_human), service: IdentityService = Depends(svc)):
    return account_out(await service.get_account(auth.account_id))


@router.patch("/me")
async def update_me(body: ProfilePatchIn, auth: AuthHuman = Depends(current_human),
                    service: IdentityService = Depends(svc)):
    return account_out(await service.update_profile(
        auth.account_id, body.display_name, body.avatar_url, body.bio))


@router.get("/sessions")
async def list_sessions(auth: AuthHuman = Depends(current_human),
                        service: IdentityService = Depends(svc)):
    return {"items": await service.list_sessions(auth.account_id, auth.session_id)}


@router.delete("/sessions/{session_id}")
async def revoke_session(session_id: str, auth: AuthHuman = Depends(current_human),
                         service: IdentityService = Depends(svc)):
    login_session = await service.revoke_session(auth.account_id, session_id)
    return {"session_id": login_session.id, "revoked_at": login_session.revoked_at.isoformat() + "Z"}


@router.post("/realtime-tickets")
async def realtime_ticket(body: TicketIn, request: Request,
                          service: IdentityService = Depends(svc)):
    """按 Bearer 主体签发一次性 WSS 票据：human→human_events，连接器→connector。"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        from aichat.core.errors import auth_invalid

        raise auth_invalid("缺少 Bearer 访问令牌")
    return await service.issue_ticket_for_bearer(auth[7:].strip(), body.audience)


@router.post("/admin/invites")
async def create_invites(body: InviteIn, auth: AuthHuman = Depends(require_admin),
                         service: IdentityService = Depends(svc)):
    invites = await service.create_invite(auth.account_id, body.note, body.expires_days, body.count)
    return {"items": [invite_out(i) for i in invites]}

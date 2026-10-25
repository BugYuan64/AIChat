from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.db import get_session
from aichat.core.deps import AuthHuman, current_human, current_connector, AuthConnector
from aichat.modules.pairing.schemas import (
    DeviceCodeIn,
    LocalConfirmIn,
    PairingCreateIn,
    PairingDecisionIn,
    RefreshCredentialIn,
    RevokeIn,
)
from aichat.modules.pairing.service import PairingService

router = APIRouter(tags=["pairing"])


def svc(request: Request, session: AsyncSession = Depends(get_session)) -> PairingService:
    return PairingService(request.app.state.ctx, session)


# ---- 匿名（连接器本机）入口：受限速 ----


@router.post("/pairings", status_code=201)
async def create_pairing(body: PairingCreateIn, request: Request, service: PairingService = Depends(svc)):
    client_ip = request.client.host if request.client else ""
    return await service.create_pairing(body, client_ip=client_ip)


@router.post("/pairing-status")
async def pairing_status(body: DeviceCodeIn, service: PairingService = Depends(svc)):
    return await service.poll_status(body.device_code)


@router.post("/pairing-local-confirmation")
async def local_confirm(body: LocalConfirmIn, service: PairingService = Depends(svc)):
    return await service.local_confirm(body.device_code, body.confirmed)


@router.post("/pairing-token")
async def redeem(body: DeviceCodeIn, service: PairingService = Depends(svc)):
    return await service.redeem_token(body.device_code)


@router.post("/connectors/access-tokens")
async def refresh_token(body: RefreshCredentialIn, service: PairingService = Depends(svc)):
    return await service.refresh_access_token(body.refresh_credential)


# ---- 已登录人类（App 侧）入口 ----


@router.get("/pairings/{pairing_id}")
async def get_pairing(pairing_id: str, code: str, auth: AuthHuman = Depends(current_human),
                      service: PairingService = Depends(svc)):
    return await service.get_pairing_for_app(pairing_id, code)


@router.post("/pairings/{pairing_id}/decision")
async def decide(pairing_id: str, body: PairingDecisionIn, auth: AuthHuman = Depends(current_human),
                 service: PairingService = Depends(svc)):
    return await service.decide(pairing_id, auth.account_id, body.decision == "approve",
                                body.confirm_code, body.expected_version)


# ---- 所有者管理 ----


@router.get("/agents/{agent_id}/connectors")
async def list_connectors(agent_id: str, auth: AuthHuman = Depends(current_human),
                          service: PairingService = Depends(svc)):
    return {"items": await service.list_connectors(agent_id, auth.account_id)}


@router.post("/connectors/{connector_id}/revoke")
async def revoke_connector(connector_id: str, body: RevokeIn, auth: AuthHuman = Depends(current_human),
                           service: PairingService = Depends(svc)):
    return await service.revoke_connector(connector_id, auth.account_id, body.reason)

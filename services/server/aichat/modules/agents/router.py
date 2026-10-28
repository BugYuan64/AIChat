from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.db import get_session
from aichat.core.deps import AuthHuman, current_human, require_admin
from aichat.modules.agents.schemas import (
    AgentCreateIn,
    AgentPatchIn,
    AgentPolicyIn,
    GrantIn,
    ModelBindingIn,
    ProviderEndpointIn,
    grant_out,
)
from aichat.modules.agents.service import AgentsService
from aichat.modules.identity.models import Account

router = APIRouter(tags=["agents"])


def svc(request: Request, session: AsyncSession = Depends(get_session)) -> AgentsService:
    return AgentsService(request.app.state.ctx, session)


@router.post("/agents")
async def create_agent(body: AgentCreateIn, auth: AuthHuman = Depends(current_human),
                       service: AgentsService = Depends(svc)):
    account = await service.create_agent(auth.account_id, body.handle, body.display_name, body.bio)
    return await service.get_agent_view(account.id, auth.account_id)


@router.get("/agents")
async def list_agents(scope: str = "owned", auth: AuthHuman = Depends(current_human),
                      service: AgentsService = Depends(svc)):
    return {"items": await service.list_owned(auth.account_id)}


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, auth: AuthHuman = Depends(current_human),
                    service: AgentsService = Depends(svc)):
    return await service.get_agent_view(agent_id, auth.account_id)


@router.patch("/agents/{agent_id}/policy")
async def set_agent_policy(agent_id: str, body: AgentPolicyIn,
                           auth: AuthHuman = Depends(current_human),
                           service: AgentsService = Depends(svc)):
    """设置 CLI 执行权限模式与工作目录（仅所有者）。"""
    profile = await service.set_policy(agent_id, auth.account_id,
                                       body.permission_mode, body.workspace_dir)
    return {
        "agent_id": profile.account_id,
        "policy": {
            "permission_mode": profile.permission_mode,
            "workspace_dir": profile.workspace_dir,
            "policy_version": profile.policy_version,
        },
    }


@router.patch("/agents/{agent_id}")
async def patch_agent(agent_id: str, body: AgentPatchIn, auth: AuthHuman = Depends(current_human),
                      service: AgentsService = Depends(svc)):
    profile = await service.require_owner(agent_id, auth.account_id)
    account = await service.session.get(Account, agent_id)
    if body.display_name is not None:
        account.display_name = body.display_name
    if body.bio is not None:
        account.bio = body.bio
    if body.status is not None:
        account.status = body.status
    return await service.get_agent_view(agent_id, auth.account_id)


@router.post("/agents/{agent_id}/model-binding")
async def set_model_binding(agent_id: str, body: ModelBindingIn, auth: AuthHuman = Depends(current_human),
                            service: AgentsService = Depends(svc)):
    binding = await service.set_model_binding(
        agent_id, auth.account_id, body.provider_code, body.credential,
        body.model_name, body.system_prompt, body.test,
    )
    return {"mode": binding.mode, "generation": str(binding.generation), "enabled": binding.enabled}


@router.post("/agents/{agent_id}/binding/revoke")
async def revoke_binding(agent_id: str, auth: AuthHuman = Depends(current_human),
                         service: AgentsService = Depends(svc)):
    await service.revoke_binding(agent_id, auth.account_id)
    return {"revoked": True}


@router.post("/agents/{agent_id}/grants")
async def add_grant(agent_id: str, body: GrantIn, auth: AuthHuman = Depends(current_human),
                    service: AgentsService = Depends(svc)):
    grant = await service.add_grant(agent_id, auth.account_id, body.human_account_id)
    account = await service.session.get(Account, grant.human_account_id)
    return grant_out(grant, account)


@router.get("/agents/{agent_id}/grants")
async def list_grants(agent_id: str, auth: AuthHuman = Depends(current_human),
                      service: AgentsService = Depends(svc)):
    rows = await service.list_grants(agent_id, auth.account_id)
    items = []
    for grant in rows:
        account = await service.session.get(Account, grant.human_account_id)
        items.append(grant_out(grant, account))
    return {"items": items}


@router.delete("/agents/{agent_id}/grants/{human_account_id}")
async def revoke_grant(agent_id: str, human_account_id: str, auth: AuthHuman = Depends(current_human),
                       service: AgentsService = Depends(svc)):
    await service.revoke_grant(agent_id, auth.account_id, human_account_id)
    return {"revoked": True}


# ---- 管理员：供应商端点白名单 ----


@router.post("/admin/provider-endpoints")
async def upsert_endpoint(body: ProviderEndpointIn, auth: AuthHuman = Depends(require_admin),
                          service: AgentsService = Depends(svc)):
    row = await service.upsert_endpoint(body.code, body.display_name, body.base_url,
                                        body.protocol, body.enabled, auth.account_id)
    return {"code": row.code, "base_url": row.base_url, "enabled": row.enabled}


@router.get("/admin/provider-endpoints")
async def list_endpoints(auth: AuthHuman = Depends(require_admin),
                         service: AgentsService = Depends(svc)):
    from sqlalchemy import select

    from aichat.modules.agents.models import ProviderEndpoint

    rows = list(await service.session.scalars(select(ProviderEndpoint)))
    return {"items": [
        {"code": r.code, "display_name": r.display_name, "base_url": r.base_url,
         "protocol": r.protocol, "enabled": r.enabled}
        for r in rows
    ]}

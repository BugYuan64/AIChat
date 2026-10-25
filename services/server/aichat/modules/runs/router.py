from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.db import get_session
from aichat.core.deps import AuthHuman, current_human
from aichat.modules.runs.service import RunsService

router = APIRouter(tags=["runs"])


def svc(request: Request, session: AsyncSession = Depends(get_session)) -> RunsService:
    return RunsService(request.app.state.ctx, session)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, auth: AuthHuman = Depends(current_human),
                  service: RunsService = Depends(svc)):
    run = await service.get_run_for_human(run_id, auth.account_id)
    return service.run_out(run)


@router.post("/runs/{run_id}/cancel")
async def cancel(run_id: str, auth: AuthHuman = Depends(current_human),
                 service: RunsService = Depends(svc)):
    run = await service.get_run_for_human(run_id, auth.account_id)
    run = await service.request_cancel(run.id)
    return service.run_out(run)


@router.post("/runs/{run_id}/retry")
async def retry(run_id: str, auth: AuthHuman = Depends(current_human),
                service: RunsService = Depends(svc)):
    await service.get_run_for_human(run_id, auth.account_id)
    run = await service.retry(run_id, auth.account_id, is_admin=auth.is_admin)
    return service.run_out(run)

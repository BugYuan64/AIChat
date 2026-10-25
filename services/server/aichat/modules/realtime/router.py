from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.db import get_session
from aichat.core.deps import AuthHuman, current_human
from aichat.modules.realtime import connector_gateway, human_ws  # noqa: F401（注册 WSS 路由）
from aichat.modules.realtime.service import RealtimeService

router = APIRouter(tags=["realtime"])


@router.get("/events")
async def events(after: str = "0", limit: int = 100, auth: AuthHuman = Depends(current_human),
                 request: Request = None, session: AsyncSession = Depends(get_session)):
    service = RealtimeService(request.app.state.ctx, session)
    try:
        after_cursor = int(after)
    except ValueError:
        from aichat.core.errors import validation_failed

        raise validation_failed("after 必须是十进制游标")
    return await service.events_page(auth.account_id, after_cursor, limit)

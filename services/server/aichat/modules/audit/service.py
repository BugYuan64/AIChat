from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.ids import new_id
from aichat.core.security import utcnow
from aichat.modules.audit.models import AuditEvent


class AuditService:
    """脱敏审计：只记录操作者、对象与摘要，不进任何秘密。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        action: str,
        object_type: str,
        object_id: str,
        *,
        actor_account_id: str | None = None,
        actor_connector_id: str | None = None,
        request_id: str | None = None,
        summary: dict | None = None,
    ) -> None:
        self.session.add(
            AuditEvent(
                id=new_id(),
                actor_account_id=actor_account_id,
                actor_connector_id=actor_connector_id,
                action=action,
                object_type=object_type,
                object_id=object_id,
                request_id=request_id,
                summary=summary or {},
            )
        )
        await self.session.flush()

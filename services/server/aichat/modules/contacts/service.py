from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.context import AppContext
from aichat.core.errors import forbidden, not_found, validation_failed
from aichat.core.ids import new_id
from aichat.core.security import utcnow
from aichat.modules.agents.models import AgentGrant, AgentProfile
from aichat.modules.audit.service import AuditService
from aichat.modules.contacts.models import Block, Contact, ContactRequest
from aichat.modules.identity.models import Account


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


class ContactsService:
    """联系人申请/关系/拉黑。AI 目标的申请由其所有者审批，接受即建立使用授权。"""

    def __init__(self, ctx: AppContext, session: AsyncSession) -> None:
        self.ctx = ctx
        self.session = session
        self.audit = AuditService(session)

    async def find_by_handle(self, handle: str) -> Account:
        account = await self.session.scalar(select(Account).where(Account.handle == handle))
        if account is None or account.status != "active":
            raise not_found("账号不存在")
        return account

    async def is_contact(self, a: str, b: str) -> bool:
        low, high = _pair(a, b)
        return await self.session.scalar(
            select(Contact.id).where(Contact.low_id == low, Contact.high_id == high)
        ) is not None

    async def is_blocked(self, a: str, b: str) -> bool:
        """任一方向拉黑即禁止私聊与邀请。"""
        return await self._blocked_between(a, b)

    async def _blocked_between(self, a: str, b: str) -> bool:
        low, high = _pair(a, b)
        rows = await self.session.scalars(
            select(Block).where(
                or_((Block.blocker_id == a) & (Block.blocked_id == b),
                    (Block.blocker_id == b) & (Block.blocked_id == a))
            )
        )
        return len(rows.all()) > 0

    async def request_contact(self, requester_id: str, target_id: str) -> ContactRequest:
        if requester_id == target_id:
            raise validation_failed("不能申请添加自己")
        target = await self.session.get(Account, target_id)
        requester = await self.session.get(Account, requester_id)
        if target is None or target.status != "active" or requester is None:
            raise not_found("目标账号不存在")
        if requester.kind != "human":
            raise forbidden("只有人类账号可以发起联系人申请")
        if await self._blocked_between(requester_id, target_id):
            raise forbidden("无法向该账号发起申请")
        if await self.is_contact(requester_id, target_id):
            raise validation_failed("已经是联系人")
        existing = await self.session.scalar(
            select(ContactRequest).where(
                ContactRequest.requester_id == requester_id,
                ContactRequest.target_id == target_id,
                ContactRequest.status == "pending",
            )
        )
        if existing is not None:
            return existing
        row = ContactRequest(id=new_id(), requester_id=requester_id, target_id=target_id)
        self.session.add(row)
        await self.audit.record("contact.request", "contact_request", row.id, actor_account_id=requester_id,
                                summary={"target": target_id, "target_kind": target.kind})
        return row

    async def decide_contact_request(self, request_id: str, decider_id: str, accept: bool) -> ContactRequest:
        row = await self.session.get(ContactRequest, request_id)
        if row is None or row.status != "pending":
            raise not_found("申请不存在或已处理")
        target = await self.session.get(Account, row.target_id)
        if target is None:
            raise not_found("目标账号不存在")
        if target.kind == "ai":
            # AI 申请由其所有者决定；接受时同时建立使用授权
            profile = await self.session.get(AgentProfile, target.id)
            if profile is None or profile.owner_account_id != decider_id:
                raise forbidden("只有 AI 所有者可以处理该申请")
        else:
            if row.target_id != decider_id:
                raise forbidden("只有被申请方可以处理该申请")
        row.status = "accepted" if accept else "rejected"
        row.decided_by = decider_id
        row.decided_at = utcnow()
        if accept:
            low, high = _pair(row.requester_id, row.target_id)
            if not await self.is_contact(row.requester_id, row.target_id):
                self.session.add(Contact(id=new_id(), low_id=low, high_id=high))
            if target.kind == "ai":
                grant = await self.session.scalar(
                    select(AgentGrant).where(AgentGrant.agent_account_id == target.id,
                                             AgentGrant.human_account_id == row.requester_id)
                )
                if grant is None:
                    self.session.add(AgentGrant(id=new_id(), agent_account_id=target.id,
                                                human_account_id=row.requester_id))
        await self.audit.record("contact.decide", "contact_request", row.id, actor_account_id=decider_id,
                                summary={"decision": row.status})
        return row

    async def pending_requests_for(self, account_id: str) -> list[tuple[ContactRequest, Account]]:
        """待我处理/我发出的申请；AI 目标的申请归其所有者处理。"""
        my_agents = list(await self.session.scalars(
            select(AgentProfile.account_id).where(AgentProfile.owner_account_id == account_id)
        ))
        target_ids = [account_id, *my_agents]
        rows = list(await self.session.scalars(
            select(ContactRequest).where(
                ContactRequest.status == "pending",
                (ContactRequest.requester_id == account_id)
                | ContactRequest.target_id.in_(target_ids),
            )
        ))
        result = []
        for row in rows:
            counterpart_id = row.target_id if row.requester_id == account_id else row.requester_id
            account = await self.session.get(Account, counterpart_id)
            result.append((row, account))
        return result

    async def list_contacts(self, account_id: str) -> list[Account]:
        rows = await self.session.scalars(
            select(Contact).where(or_(Contact.low_id == account_id, Contact.high_id == account_id))
        )
        other_ids = [(r.high_id if r.low_id == account_id else r.low_id) for r in rows]
        accounts = []
        for oid in other_ids:
            account = await self.session.get(Account, oid)
            if account is not None:
                accounts.append(account)
        return accounts

    async def remove_contact(self, account_id: str, other_id: str) -> None:
        low, high = _pair(account_id, other_id)
        row = await self.session.scalar(select(Contact).where(Contact.low_id == low, Contact.high_id == high))
        if row is not None:
            await self.session.delete(row)
            await self.audit.record("contact.remove", "contact", row.id, actor_account_id=account_id,
                                    summary={"other": other_id})

    async def block_account(self, account_id: str, other_id: str) -> None:
        if account_id == other_id:
            raise validation_failed("不能拉黑自己")
        if not await self.session.scalar(
            select(Block.id).where(Block.blocker_id == account_id, Block.blocked_id == other_id)
        ):
            self.session.add(Block(id=new_id(), blocker_id=account_id, blocked_id=other_id))
        await self.audit.record("contact.block", "account", other_id, actor_account_id=account_id)

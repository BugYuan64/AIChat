"""conversations 模块：私聊幂等创建、群与角色、成员区间与邀请。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.context import AppContext
from aichat.core.errors import forbidden, not_found, validation_failed
from aichat.core.ids import new_id
from aichat.core.outbox import emit
from aichat.core.security import utcnow
from aichat.modules.agents.models import AgentGrant, AgentProfile
from aichat.modules.audit.service import AuditService
from aichat.modules.contacts.service import ContactsService
from aichat.modules.conversations.models import (
    Conversation,
    DirectPair,
    GroupInvitation,
    MembershipInterval,
)
from aichat.modules.identity.models import Account
from aichat.modules.messages.models import Message, ReadCursor
from aichat.modules.messages.service import MessagesService


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


class ConversationsService:
    def __init__(self, ctx: AppContext, session: AsyncSession) -> None:
        self.ctx = ctx
        self.session = session
        self.messages = MessagesService(ctx, session)
        self.contacts = ContactsService(ctx, session)
        self.audit = AuditService(session)

    # ---- 私聊 ----

    async def create_direct(self, requester_id: str, target_id: str) -> tuple[Conversation, bool]:
        """幂等：同无序账号对已存在则返回原会话（created=False）。"""
        if requester_id == target_id:
            raise validation_failed("不能与自己创建私聊")
        target = await self.session.get(Account, target_id)
        requester = await self.session.get(Account, requester_id)
        if target is None or target.status != "active" or requester is None:
            raise not_found("目标账号不存在")
        low, high = _pair(requester_id, target_id)
        existing = await self.session.scalar(
            select(DirectPair).where(DirectPair.low_id == low, DirectPair.high_id == high)
        )
        if existing is not None:
            conv = await self.session.get(Conversation, existing.conversation_id)
            if conv is None:
                raise not_found("会话不存在")
            return conv, False
        # 授权：人类目标需为联系人；AI 目标需有使用授权
        if target.kind == "ai":
            if not await self.messages.has_active_grant(target_id, requester_id):
                raise forbidden("尚未获得该 AI 的使用授权")
        else:
            if not await self.contacts.is_contact(requester_id, target_id):
                raise forbidden("双方不是联系人")
        if await self.contacts.is_blocked(requester_id, target_id):
            raise forbidden("无法与该账号创建私聊")

        conv = Conversation(id=new_id(), kind="direct")
        self.session.add(conv)
        await self.session.flush()
        self.session.add(DirectPair(conversation_id=conv.id, low_id=low, high_id=high))
        for account_id in (low, high):
            self.session.add(MembershipInterval(
                id=new_id(), conversation_id=conv.id, account_id=account_id,
                role="member", joined_seq=1,
            ))
        await self.audit.record("conversation.create", "conversation", conv.id,
                                actor_account_id=requester_id, summary={"kind": "direct"})
        return conv, True

    # ---- 群聊 ----

    async def create_group(self, creator_id: str, title: str, member_ids: list[str]) -> tuple[Conversation, list[GroupInvitation]]:
        creator = await self.session.get(Account, creator_id)
        if creator is None or creator.kind != "human":
            raise forbidden("只有人类账号可以建群")
        conv = Conversation(id=new_id(), kind="group", title=title, owner_account_id=creator_id)
        self.session.add(conv)
        await self.session.flush()
        self.session.add(MembershipInterval(
            id=new_id(), conversation_id=conv.id, account_id=creator_id,
            role="owner", joined_seq=1,
        ))
        invitations: list[GroupInvitation] = []
        for member_id in dict.fromkeys(member_ids):
            if member_id == creator_id:
                continue
            member = await self.session.get(Account, member_id)
            if member is None or member.status != "active":
                raise validation_failed("成员账号不可用")
            if member.kind == "ai":
                if not await self.messages.has_active_grant(member_id, creator_id):
                    raise forbidden(f"未获得 AI {member.handle} 的使用授权")
            else:
                if not await self.contacts.is_contact(creator_id, member_id):
                    raise validation_failed(f"{member.handle} 不是你的联系人")
            invitation = GroupInvitation(
                id=new_id(), conversation_id=conv.id, target_account_id=member_id,
                inviter_id=creator_id,
            )
            self.session.add(invitation)
            invitations.append(invitation)
        await self.messages.create_system_message(conv, f"群聊已创建")
        await self.audit.record("conversation.create", "conversation", conv.id,
                                actor_account_id=creator_id, summary={"kind": "group", "title": title})
        return conv, invitations

    async def invite(self, conversation_id: str, inviter_id: str, target_id: str) -> GroupInvitation:
        conv = await self.messages.get_conversation(conversation_id, lock=True)
        if conv.kind != "group" or conv.status != "active":
            raise validation_failed("仅活跃群聊可以邀请")
        inviter_membership = await self.messages.active_membership(conversation_id, inviter_id)
        if inviter_membership is None or inviter_membership.role not in ("owner", "admin"):
            raise forbidden("只有群主或管理员可以邀请")
        target = await self.session.get(Account, target_id)
        if target is None or target.status != "active":
            raise not_found("目标账号不存在")
        if await self.messages.active_membership(conversation_id, target_id) is not None:
            raise validation_failed("该账号已是成员")
        existing = await self.session.scalar(
            select(GroupInvitation).where(
                GroupInvitation.conversation_id == conversation_id,
                GroupInvitation.target_account_id == target_id,
                GroupInvitation.status == "pending",
            )
        )
        if existing is not None:
            return existing
        if target.kind == "ai" and not await self.messages.has_active_grant(target_id, inviter_id):
            raise forbidden("未获得该 AI 的使用授权")
        invitation = GroupInvitation(
            id=new_id(), conversation_id=conversation_id, target_account_id=target_id, inviter_id=inviter_id
        )
        self.session.add(invitation)
        await self.audit.record("member.invite", "conversation", conversation_id,
                                actor_account_id=inviter_id, summary={"target": target_id})
        return invitation

    async def decide_invitation(self, invitation_id: str, decider_id: str, accept: bool) -> GroupInvitation:
        invitation = await self.session.get(GroupInvitation, invitation_id)
        if invitation is None or invitation.status != "pending":
            raise not_found("邀请不存在或已处理")
        conv = await self.messages.get_conversation(invitation.conversation_id, lock=True)
        if conv.status != "active":
            raise validation_failed("会话已关闭")
        target = await self.session.get(Account, invitation.target_account_id)
        if target is None:
            raise not_found("目标账号不存在")
        # 人类邀请由本人决定；AI 邀请由其所有者决定
        if target.kind == "ai":
            profile = await self.session.get(AgentProfile, target.id)
            if profile is None or profile.owner_account_id != decider_id:
                raise forbidden("只有 AI 所有者可以处理该邀请")
        else:
            if invitation.target_account_id != decider_id:
                raise forbidden("只有被邀请者可以处理该邀请")

        invitation.status = "accepted" if accept else "rejected"
        invitation.decided_at = utcnow()
        if accept:
            conv.permission_version += 1
            display = target.display_name
            await self.messages.create_system_message(conv, f"{display} 加入了群聊")
            # 加入系统消息（刚分配的 last_seq）成为新成员第一条可见消息
            membership = MembershipInterval(
                id=new_id(), conversation_id=conv.id, account_id=target.id,
                role="member", joined_seq=conv.last_seq,
            )
            self.session.add(membership)
            await emit(
                self.session, "membership.changed",
                {
                    "conversation_id": conv.id,
                    "membership_id": membership.id,
                    "account_id": target.id,
                    "change": "joined",
                    "role": membership.role,
                    "permission_version": conv.permission_version,
                    "subject_account_id": target.id,
                },
                conversation_id=conv.id,
                subject_account_ids=[target.id],
            )
        await self.audit.record("member.invite.decide", "conversation", conv.id,
                                actor_account_id=decider_id,
                                summary={"invitation": invitation_id, "decision": invitation.status})
        return invitation

    async def remove_member(self, conversation_id: str, actor_id: str, membership_id: str) -> MembershipInterval:
        conv = await self.messages.get_conversation(conversation_id, lock=True)
        if conv.kind != "group" or conv.status != "active":
            raise validation_failed("仅活跃群聊支持移除成员")
        membership = await self.session.get(MembershipInterval, membership_id)
        if membership is None or membership.conversation_id != conversation_id or membership.left_at is not None:
            raise not_found("成员不存在")
        actor_membership = await self.messages.active_membership(conversation_id, actor_id)
        if actor_membership is None:
            raise forbidden("不是该群成员")
        is_self = membership.account_id == actor_id
        if not is_self:
            if actor_membership.role not in ("owner", "admin"):
                raise forbidden("只有群主或管理员可以移除成员")
            if actor_membership.role == "admin" and membership.role in ("owner", "admin"):
                raise forbidden("管理员不能移除群主或其他管理员")
        else:
            if membership.role == "owner":
                raise forbidden("群主需先转让群主或解散群聊")
        return await self._leave(conv, membership)

    async def _leave(self, conv: Conversation, membership: MembershipInterval) -> MembershipInterval:
        membership.left_seq = conv.last_seq
        membership.left_at = utcnow()
        conv.permission_version += 1
        account = await self.session.get(Account, membership.account_id)
        display = account.display_name if account else membership.account_id
        await self.messages.create_system_message(conv, f"{display} 离开了群聊")
        await emit(
            self.session, "membership.changed",
            {
                "conversation_id": conv.id,
                "membership_id": membership.id,
                "account_id": membership.account_id,
                "change": "left",
                "permission_version": conv.permission_version,
                "subject_account_id": membership.account_id,
            },
            conversation_id=conv.id,
            subject_account_ids=[membership.account_id],
        )
        # AI 所有者退群/被移除 → 其在群内的 AI 一并移除；在途任务取消
        if account is not None and account.kind == "human":
            profiles = await self.session.scalars(
                select(AgentProfile).where(AgentProfile.owner_account_id == account.id)
            )
            for profile in profiles:
                ai_membership = await self.messages.active_membership(conv.id, profile.account_id)
                if ai_membership is not None:
                    await self._leave(conv, ai_membership)
        from aichat.modules.runs.models import Run

        from aichat.modules.runs.service import RunsService

        runs_service = RunsService(self.ctx, self.session)
        active_runs = list(await self.session.scalars(
            select(Run).where(
                Run.conversation_id == conv.id,
                Run.agent_account_id == membership.account_id,
                Run.state.in_(("queued", "dispatched", "running", "cancel_requested")),
            )
        ))
        for run in active_runs:
            if run.state == "queued":
                run.state = "cancelled"
                await runs_service.emit_run_updated(run)
            else:
                run.state = "cancelled"
                await runs_service.emit_run_updated(run)
                # 连接器在途执行：通知取消（尽力而为）
                attempt = await runs_service.current_attempt(run.id)
                if attempt is not None and attempt.connector_id:
                    await self.ctx.hub.send_to_connector(
                        attempt.connector_id,
                        {"type": "run.cancel", "run_id": run.id, "execution_id": attempt.execution_id,
                         "reason": "membership_revoked"},
                    )
                else:
                    self.ctx.cancel_flags.cancel(run.id)
        return membership

    async def dissolve(self, conversation_id: str, actor_id: str) -> Conversation:
        conv = await self.messages.get_conversation(conversation_id, lock=True)
        if conv.kind != "group":
            raise validation_failed("仅群聊支持解散")
        membership = await self.messages.active_membership(conversation_id, actor_id)
        if membership is None or membership.role != "owner":
            raise forbidden("只有群主可以解散群聊")
        conv.status = "closed"
        conv.permission_version += 1
        await self.messages.create_system_message(conv, "群聊已解散")
        await emit(self.session, "conversation.closed",
                  {"conversation_id": conv.id, "permission_version": conv.permission_version},
                  conversation_id=conv.id)
        await self.audit.record("conversation.dissolve", "conversation", conv.id, actor_account_id=actor_id)
        return conv

    # ---- 查询 ----

    async def list_for_account(self, account_id: str, limit: int = 100) -> list[dict]:
        memberships = list(await self.session.scalars(
            select(MembershipInterval).where(
                MembershipInterval.account_id == account_id,
                MembershipInterval.left_at.is_(None),
            ).limit(limit)
        ))
        items = []
        for membership in memberships:
            conv = await self.session.get(Conversation, membership.conversation_id)
            if conv is None:
                continue
            last_message = await self.session.scalar(
                select(Message).where(Message.conversation_id == conv.id)
                .order_by(Message.seq.desc()).limit(1)
            )
            cursor = await self.session.get(ReadCursor, (conv.id, account_id))
            read_seq = cursor.read_seq if cursor else 0
            others = []
            for other_id in await self.messages.member_account_ids(conv.id):
                if other_id != account_id:
                    other = await self.session.get(Account, other_id)
                    if other is not None:
                        others.append({"account_id": other.id, "kind": other.kind,
                                       "display_name": other.display_name})
            items.append({
                "conversation_id": conv.id,
                "kind": conv.kind,
                "title": conv.title or (others[0]["display_name"] if others else "私聊"),
                "members": others if conv.kind == "direct" else None,
                "member_count": len(others) + 1,
                "last_message": (
                    {"message_id": last_message.id, "seq": str(last_message.seq),
                     "kind": last_message.kind,
                     "text": (last_message.text[:64] if last_message.text else ""),
                     "status": last_message.status,
                     "created_at": last_message.created_at.isoformat() + "Z"}
                    if last_message else None
                ),
                "last_seq": str(conv.last_seq),
                "unread": str(max(0, conv.last_seq - read_seq)),
                "role": membership.role,
                "status": conv.status,
                "updated_at": conv.updated_at.isoformat() + "Z",
            })
        items.sort(key=lambda i: i["updated_at"], reverse=True)
        return items

    async def conversation_detail(self, conversation_id: str, account_id: str) -> dict:
        conv = await self.messages.get_conversation(conversation_id)
        membership = await self.messages.active_membership(conversation_id, account_id)
        if membership is None:
            raise forbidden("不是该会话成员")
        members = []
        for row in await self.session.scalars(
            select(MembershipInterval).where(
                MembershipInterval.conversation_id == conversation_id,
                MembershipInterval.left_at.is_(None),
            )
        ):
            account = await self.session.get(Account, row.account_id)
            if account is None:
                continue
            members.append({
                "membership_id": row.id,
                "account_id": account.id,
                "kind": account.kind,
                "handle": account.handle,
                "display_name": account.display_name,
                "role": row.role,
                "joined_seq": str(row.joined_seq),
            })
        return {
            "conversation_id": conv.id,
            "kind": conv.kind,
            "title": conv.title,
            "status": conv.status,
            "permission_version": str(conv.permission_version),
            "last_seq": str(conv.last_seq),
            "members": members,
            "visible_from_seq": str(membership.joined_seq),
        }

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.config import Settings
from aichat.core.context import AppContext
from aichat.core.errors import ApiError, auth_invalid, not_found, rate_limited, validation_failed
from aichat.core.ids import new_id
from aichat.core.security import (
    create_access_token,
    hash_password,
    random_token,
    sha256_hex,
    utcnow,
    verify_password,
)
from aichat.modules.audit.service import AuditService
from aichat.modules.identity.models import Account, HumanCredential, Invite, LoginSession, WsTicket


class IdentityService:
    """人类身份：邀请注册、登录会话轮换、一次性 WSS 票据。"""

    def __init__(self, ctx: AppContext, session: AsyncSession) -> None:
        self.ctx = ctx
        self.settings: Settings = ctx.settings
        self.session = session
        self.audit = AuditService(session)

    # ---- 账号 ----

    async def register(self, invite_code: str, handle: str, display_name: str, password: str) -> Account:
        invite = await self.session.get(Invite, invite_code)
        if invite is None or invite.used_by is not None:
            raise validation_failed("邀请码无效或已被使用")
        if invite.expires_at is not None and invite.expires_at <= utcnow():
            raise validation_failed("邀请码已过期")
        dup = await self.session.scalar(select(Account).where(Account.handle == handle))
        if dup is not None:
            raise validation_failed("账号名已被占用")
        account = Account(id=new_id(), kind="human", handle=handle, display_name=display_name)
        self.session.add(account)
        self.session.add(HumanCredential(account_id=account.id, password_hash=hash_password(password)))
        invite.used_by = account.id
        invite.used_at = utcnow()
        await self.audit.record("account.register", "account", account.id, actor_account_id=account.id,
                                summary={"handle": handle, "invite_note": invite.note})
        return account

    async def get_account(self, account_id: str) -> Account:
        account = await self.session.get(Account, account_id)
        if account is None:
            raise not_found("账号不存在")
        return account

    async def create_invite(self, admin_account_id: str, note: str | None, expires_days: int, count: int = 1) -> list[Invite]:
        invites = []
        for _ in range(count):
            invite = Invite(code=random_token(18), created_by=admin_account_id, note=note,
                            expires_at=utcnow() + timedelta(days=expires_days))
            self.session.add(invite)
            invites.append(invite)
        await self.audit.record("invite.create", "invite", "batch", actor_account_id=admin_account_id,
                                summary={"count": count, "note": note})
        return invites

    # ---- 登录会话 ----

    async def login(self, handle: str, password: str, device_summary: str | None, *, client_ip: str = "") -> dict:
        limiter = self.ctx.limiter
        limiter.check(f"login:{client_ip or handle}", self.settings.rate_limit_login_per_min)
        account = await self.session.scalar(select(Account).where(Account.handle == handle))
        credential = await self.session.get(HumanCredential, account.id) if account else None
        if account is None or credential is None or account.kind != "human" or account.status != "active":
            raise auth_invalid("账号名或密码错误")
        if not verify_password(password, credential.password_hash):
            raise auth_invalid("账号名或密码错误")
        return await self._issue_session(account, device_summary)

    async def refresh(self, refresh_token: str) -> dict:
        refresh_hash = sha256_hex(refresh_token)
        login_session = await self.session.scalar(select(LoginSession).where(LoginSession.refresh_hash == refresh_hash))
        if login_session is None:
            raise auth_invalid("刷新凭据无效")
        if login_session.revoked_at is not None or login_session.expires_at <= utcnow():
            raise auth_invalid("刷新凭据已失效")
        account = await self.session.get(Account, login_session.account_id)
        if account is None or account.status != "active":
            raise auth_invalid("账号不可用")
        # 轮换：旧刷新凭据立即失效
        login_session.revoked_at = utcnow()
        await self.audit.record("session.rotate", "login_session", login_session.id,
                                actor_account_id=account.id)
        return await self._issue_session(account, login_session.device_summary)

    async def _issue_session(self, account: Account, device_summary: str | None) -> dict:
        refresh_token = random_token(32)
        login_session = LoginSession(
            id=new_id(),
            account_id=account.id,
            refresh_hash=sha256_hex(refresh_token),
            device_summary=device_summary,
            expires_at=utcnow() + timedelta(days=self.settings.refresh_token_days),
        )
        self.session.add(login_session)
        await self.session.flush()
        access_token, _ = create_access_token(
            self.settings,
            subject_type="human",
            subject_id=account.id,
            audience="human",
            expires_in=self.settings.access_token_seconds,
            extra_claims={"sid": login_session.id},
        )
        await self.audit.record("session.create", "login_session", login_session.id,
                                actor_account_id=account.id, summary={"device": device_summary})
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": self.settings.access_token_seconds,
        }

    async def logout(self, account_id: str, session_id: str) -> None:
        login_session = await self.session.get(LoginSession, session_id)
        if login_session is not None and login_session.account_id == account_id:
            login_session.revoked_at = utcnow()
            await self.audit.record("session.revoke", "login_session", session_id, actor_account_id=account_id)

    # ---- WSS 票据 ----

    async def create_ws_ticket(self, subject_type: str, subject_id: str, audience: str) -> dict:
        ticket = random_token(24)
        self.session.add(
            WsTicket(
                id=new_id(),
                subject_type=subject_type,
                subject_id=subject_id,
                audience=audience,
                ticket_hash=sha256_hex(ticket),
                expires_at=utcnow() + timedelta(seconds=self.settings.ws_ticket_seconds),
            )
        )
        await self.session.flush()
        return {"ticket": ticket, "expires_in": self.settings.ws_ticket_seconds}

    async def issue_ticket_for_bearer(self, bearer_token: str, audience: str) -> dict:
        """按 Bearer 令牌主体签发对应受众的 WSS 票据（人类/连接器不可互换）。"""
        from aichat.core.errors import validation_failed
        from aichat.core.security import decode_access_token

        if audience == "human_events":
            claims = decode_access_token(self.settings, bearer_token, audience="human")
            if claims.get("sub_typ") != "human":
                raise auth_invalid("令牌主体类型不匹配")
            login_session = await self.session.get(LoginSession, claims.get("sid", ""))
            account = await self.session.get(Account, claims["sub"])
            if (login_session is None or login_session.revoked_at is not None
                    or login_session.expires_at <= utcnow()
                    or account is None or account.status != "active"):
                raise auth_invalid("登录状态无效")
            return await self.create_ws_ticket("human", account.id, audience)
        if audience == "connector":
            from aichat.modules.pairing.models import Connector

            claims = decode_access_token(self.settings, bearer_token, audience="connector")
            if claims.get("sub_typ") != "connector":
                raise auth_invalid("令牌主体类型不匹配")
            connector = await self.session.get(Connector, claims["sub"])
            if connector is None or connector.revoked_at is not None:
                raise auth_invalid("连接器凭据无效")
            if connector.credential_version != int(claims.get("cred_ver", -1)):
                raise auth_invalid("连接器凭据版本已更新")
            return await self.create_ws_ticket("connector", connector.id, audience)
        raise validation_failed("未知的票据受众")

    async def consume_ws_ticket(self, ticket: str, audience: str) -> str:
        """一次性消费，返回 subject_id。"""
        ws_ticket = await self.session.scalar(
            select(WsTicket).where(WsTicket.ticket_hash == sha256_hex(ticket), WsTicket.audience == audience)
        )
        if ws_ticket is None or ws_ticket.consumed_at is not None or ws_ticket.expires_at <= utcnow():
            raise auth_invalid("实时票据无效或已使用")
        ws_ticket.consumed_at = utcnow()
        return ws_ticket.subject_id

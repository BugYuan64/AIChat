from datetime import timedelta

from sqlalchemy import or_, select, update
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
from aichat.modules.identity.schemas import account_out


class IdentityService:
    """人类身份：邀请注册、登录会话轮换、一次性 WSS 票据。"""

    def __init__(self, ctx: AppContext, session: AsyncSession) -> None:
        self.ctx = ctx
        self.settings: Settings = ctx.settings
        self.session = session
        self.audit = AuditService(session)

    # ---- 账号 ----

    async def register(self, invite_code: str, handle: str, display_name: str, password: str) -> Account:
        dup = await self.session.scalar(select(Account).where(Account.handle == handle))
        if dup is not None:
            raise validation_failed("账号名已被占用")
        account = Account(id=new_id(), kind="human", handle=handle, display_name=display_name)
        now = utcnow()
        claimed = (await self.session.execute(
            update(Invite).where(Invite.code == invite_code, Invite.used_by.is_(None),
                                 or_(Invite.expires_at.is_(None), Invite.expires_at > now))
            .values(used_by=account.id, used_at=now).returning(Invite.code, Invite.note)
        )).first()
        if claimed is None:
            raise validation_failed("邀请码无效、已过期或已被使用")
        self.session.add(account)
        self.session.add(HumanCredential(account_id=account.id, password_hash=hash_password(password)))
        await self.audit.record("account.register", "account", account.id, actor_account_id=account.id,
                                summary={"handle": handle, "invite_note": claimed.note})
        return account

    async def get_account(self, account_id: str) -> Account:
        account = await self.session.get(Account, account_id)
        if account is None:
            raise not_found("账号不存在")
        return account

    async def update_profile(self, account_id: str, display_name: str | None,
                             avatar_url: str | None, bio: str | None) -> Account:
        account = await self.get_account(account_id)
        if display_name is not None:
            account.display_name = display_name
        if avatar_url is not None:
            account.avatar_url = avatar_url or None
        if bio is not None:
            account.bio = bio or None
        await self.audit.record("account.profile.update", "account", account.id,
                                actor_account_id=account_id,
                                summary={"fields": [k for k, v in
                                                    (("display_name", display_name), ("avatar_url", avatar_url),
                                                     ("bio", bio)) if v is not None]})
        return account

    async def list_sessions(self, account_id: str, current_session_id: str) -> list[dict]:
        rows = list(await self.session.scalars(
            select(LoginSession).where(
                LoginSession.account_id == account_id,
                LoginSession.revoked_at.is_(None),
                LoginSession.expires_at > utcnow(),
            ).order_by(LoginSession.created_at.desc())
        ))
        return [
            {
                "session_id": row.id,
                "device_summary": row.device_summary,
                "created_at": row.created_at.isoformat() + "Z",
                "last_seen_at": row.last_seen_at.isoformat() + "Z" if row.last_seen_at else None,
                "expires_at": row.expires_at.isoformat() + "Z",
                "current": row.id == current_session_id,
            }
            for row in rows
        ]

    async def revoke_session(self, account_id: str, session_id: str) -> LoginSession:
        login_session = await self.session.get(LoginSession, session_id)
        if login_session is None or login_session.account_id != account_id:
            raise not_found("会话不存在")
        login_session.revoked_at = utcnow()
        await self.audit.record("session.revoke", "login_session", session_id,
                                actor_account_id=account_id)
        # 撤销立即生效：断开该会话签发的全部 WSS 连接
        await self.ctx.hub.kick_session(session_id)
        return login_session

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
        now = utcnow()
        login_session = (await self.session.execute(
            update(LoginSession).where(LoginSession.refresh_hash == refresh_hash,
                                       LoginSession.revoked_at.is_(None), LoginSession.expires_at > now)
            .values(revoked_at=now)
            .returning(LoginSession.id, LoginSession.account_id, LoginSession.device_summary)
        )).first()
        if login_session is None:
            raise auth_invalid("刷新凭据已失效")
        account = await self.session.get(Account, login_session.account_id)
        if account is None or account.status != "active":
            raise auth_invalid("账号不可用")
        # 轮换：旧刷新凭据立即失效
        await self.audit.record("session.rotate", "login_session", login_session.id,
                                actor_account_id=account.id)
        await self.ctx.hub.kick_session(login_session.id)
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
            "account": account_out(account),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": self.settings.access_token_seconds,
        }

    async def logout(self, account_id: str, session_id: str) -> None:
        login_session = await self.session.get(LoginSession, session_id)
        if login_session is not None and login_session.account_id == account_id:
            login_session.revoked_at = utcnow()
            await self.audit.record("session.revoke", "login_session", session_id, actor_account_id=account_id)
            await self.ctx.hub.kick_session(session_id)

    # ---- WSS 票据 ----

    async def create_ws_ticket(self, subject_type: str, subject_id: str, audience: str,
                               session_id: str | None = None) -> dict:
        ticket = random_token(24)
        self.session.add(
            WsTicket(
                id=new_id(),
                subject_type=subject_type,
                subject_id=subject_id,
                session_id=session_id if subject_type == "human" else None,
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
            return await self.create_ws_ticket("human", account.id, audience, session_id=login_session.id)
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

    async def consume_ws_ticket(self, ticket: str, audience: str) -> tuple[str, str | None]:
        """一次性消费，返回 (subject_id, session_id)；session_id 仅人类票据非空。"""
        # Conditional update serializes competing handshakes on PostgreSQL and SQLite.
        now = utcnow()
        result = await self.session.execute(
            update(WsTicket).where(WsTicket.ticket_hash == sha256_hex(ticket),
                                   WsTicket.audience == audience, WsTicket.consumed_at.is_(None),
                                   WsTicket.expires_at > now)
            .values(consumed_at=now).returning(WsTicket.subject_id, WsTicket.session_id)
        )
        consumed = result.first()
        if consumed is None:
            raise auth_invalid("实时票据无效或已使用")
        subject_id, session_id = consumed
        if audience == "human_events":
            login = await self.session.get(LoginSession, session_id) if session_id else None
            account = await self.session.get(Account, subject_id)
            if (login is None or login.account_id != subject_id or login.revoked_at is not None
                    or login.expires_at <= now or account is None or account.status != "active"):
                raise auth_invalid("登录状态无效")
        return subject_id, session_id

"""HTTP 认证依赖：人类（login session）与连接器（绑定凭据）两类主体，票据受众不可互换。"""

from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.context import AppContext
from aichat.core.db import get_session
from aichat.core.errors import auth_invalid, forbidden, session_revoked
from aichat.core.security import decode_access_token, utcnow
from aichat.modules.identity.models import Account, LoginSession
from aichat.modules.pairing.models import Connector


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


@dataclass
class AuthHuman:
    account_id: str
    session_id: str
    is_admin: bool


@dataclass
class AuthConnector:
    connector_id: str
    agent_account_id: str
    owner_account_id: str
    credential_version: int


def _bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise auth_invalid("缺少 Bearer 访问令牌")
    return auth[7:].strip()


async def current_human(
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
) -> AuthHuman:
    claims = decode_access_token(ctx.settings, _bearer(request), audience="human")
    if claims.get("sub_typ") != "human":
        raise auth_invalid("令牌主体类型不匹配")
    account_id, session_id = claims["sub"], claims.get("sid", "")
    login_session = await session.get(LoginSession, session_id)
    if login_session is None or login_session.account_id != account_id:
        raise auth_invalid("登录会话不存在")
    if login_session.revoked_at is not None:
        raise session_revoked()
    if login_session.expires_at <= utcnow():
        raise auth_invalid("登录会话已过期")
    account = await session.get(Account, account_id)
    if account is None or account.status != "active" or account.kind != "human":
        raise session_revoked("账号不可用")
    login_session.last_seen_at = utcnow()
    return AuthHuman(account_id=account_id, session_id=session_id, is_admin=account.is_admin)


async def require_admin(auth: AuthHuman = Depends(current_human)) -> AuthHuman:
    if not auth.is_admin:
        raise forbidden("需要管理员权限")
    return auth


async def current_connector(
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
) -> AuthConnector:
    claims = decode_access_token(ctx.settings, _bearer(request), audience="connector")
    if claims.get("sub_typ") != "connector":
        raise auth_invalid("令牌主体类型不匹配")
    connector_id = claims["sub"]
    connector = await session.get(Connector, connector_id)
    if connector is None or connector.revoked_at is not None:
        raise session_revoked("连接器已撤销")
    if connector.credential_version != int(claims.get("cred_ver", -1)):
        raise session_revoked("连接器凭据已更新")
    connector.last_seen_at = utcnow()
    return AuthConnector(
        connector_id=connector_id,
        agent_account_id=connector.agent_account_id,
        owner_account_id=connector.owner_account_id,
        credential_version=connector.credential_version,
    )


def refresh_expiry(days: int) -> object:
    return utcnow() + timedelta(days=days)

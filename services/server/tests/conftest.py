"""集成测试公共设施：文件 SQLite + ASGI 客户端（不起后台循环，确定性）。"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from aichat.app import create_app
from aichat.core.config import Settings
from aichat.core.context import AppContext, CancelFlags
from aichat.core.db import Database
from aichat.core.security import CredentialCipher
from aichat.modules.realtime.hub import RealtimeHub


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path.as_posix()}/test.db",
        jwt_secret="test-secret",
    )


@pytest_asyncio.fixture()
async def ctx(settings) -> AppContext:
    context = AppContext(
        settings=settings,
        db=Database(settings),
        hub=RealtimeHub(),
        cipher=CredentialCipher(settings),
        cancel_flags=CancelFlags(),
    )
    await context.db.create_all()
    yield context
    await context.db.dispose()


@pytest_asyncio.fixture()
async def app(ctx):
    application = create_app(settings=ctx.settings)
    application.state.ctx = ctx
    return application


@pytest_asyncio.fixture()
async def client(app) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def auth_headers(client: AsyncClient, token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def make_admin(ctx) -> str:
    from datetime import timedelta

    from aichat.core.ids import new_id
    from aichat.core.security import hash_password, random_token, utcnow
    from aichat.modules.identity.models import Account, HumanCredential, Invite

    async with ctx.db.session_factory() as session:
        account = Account(id=new_id(), kind="human", handle="admin", display_name="管理员", is_admin=True)
        session.add(account)
        session.add(HumanCredential(account_id=account.id, password_hash=hash_password("admin-password-123")))
        invite_codes = []
        for _ in range(20):
            code = random_token(18)
            session.add(Invite(code=code, expires_at=utcnow() + timedelta(days=1)))
            invite_codes.append(code)
        await session.commit()
        return account.id, invite_codes


async def register_user(client: AsyncClient, invite_code: str, handle: str,
                        password: str = "password-123456") -> dict:
    resp = await client.post("/v1/auth/register", json={
        "invite_code": invite_code, "handle": handle,
        "display_name": handle.upper(), "password": password,
    })
    assert resp.status_code == 200, resp.text
    login = await client.post("/v1/auth/login", json={"handle": handle, "password": password})
    assert login.status_code == 200, login.text
    return {"account_id": resp.json()["data"]["account_id"],
            "token": login.json()["data"]["access_token"]}

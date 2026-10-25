"""引导 CLI：初始化库、创建管理员、发放邀请、维护供应商白名单。

用法：
  python -m aichat.bootstrap init-db
  python -m aichat.bootstrap admin --handle admin --password <pwd> [--display-name 管理员]
  python -m aichat.bootstrap invite --count 5 [--note dev]
  python -m aichat.bootstrap provider --code glm --name 智谱 --base-url https://open.bigmodel.cn/api/paas/v4
"""

import argparse
import asyncio
import getpass

from sqlalchemy import select

from aichat.core.config import get_settings
from aichat.core.context import AppContext, CancelFlags
from aichat.core.db import Database
from aichat.core.errors import ApiError
from aichat.core.ids import new_id
from aichat.core.security import CredentialCipher, hash_password, utcnow
from aichat.modules.agents.models import ProviderEndpoint
from aichat.modules.audit.service import AuditService
from aichat.modules.identity.models import Account, HumanCredential, Invite
from aichat.modules.realtime.hub import RealtimeHub


def build_context() -> AppContext:
    settings = get_settings()
    return AppContext(settings=settings, db=Database(settings), hub=RealtimeHub(),
                      cipher=CredentialCipher(settings), cancel_flags=CancelFlags())


async def init_db(ctx: AppContext) -> None:
    await ctx.db.create_all()
    print("数据库结构已初始化")


async def create_admin(ctx: AppContext, handle: str, password: str, display_name: str) -> None:
    async with ctx.db.session_factory() as session:
        dup = await session.scalar(select(Account).where(Account.handle == handle))
        if dup is not None:
            print(f"账号 {handle} 已存在")
            return
        account = Account(id=new_id(), kind="human", handle=handle, display_name=display_name,
                          is_admin=True)
        session.add(account)
        session.add(HumanCredential(account_id=account.id, password_hash=hash_password(password)))
        await AuditService(session).record("account.bootstrap_admin", "account", account.id,
                                           actor_account_id=account.id)
        await session.commit()
        print(f"管理员已创建：{handle} (account_id={account.id})")


async def create_invites(ctx: AppContext, count: int, note: str | None) -> None:
    from datetime import timedelta

    from aichat.core.security import random_token

    async with ctx.db.session_factory() as session:
        codes = []
        for _ in range(count):
            code = random_token(18)
            session.add(Invite(code=code, note=note,
                               expires_at=utcnow() + timedelta(days=7)))
            codes.append(code)
        await session.commit()
        print("邀请码（7 天有效）：")
        for code in codes:
            print(f"  {code}")


async def add_provider(ctx: AppContext, code: str, name: str, base_url: str) -> None:
    async with ctx.db.session_factory() as session:
        row = await session.get(ProviderEndpoint, code)
        if row is None:
            session.add(ProviderEndpoint(code=code, display_name=name, base_url=base_url))
        else:
            row.display_name = name
            row.base_url = base_url
        await session.commit()
        print(f"供应商端点已保存：{code} → {base_url}")


async def _run(args) -> None:
    ctx = build_context()
    if args.command == "init-db":
        await init_db(ctx)
    elif args.command == "admin":
        password = args.password or getpass.getpass("管理员密码：")
        await create_admin(ctx, args.handle, password, args.display_name)
    elif args.command == "invite":
        await create_invites(ctx, args.count, args.note)
    elif args.command == "provider":
        await add_provider(ctx, args.code, args.name, args.base_url)
    await ctx.db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="aichat-bootstrap")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="创建数据库结构")

    p_admin = sub.add_parser("admin", help="创建管理员账号")
    p_admin.add_argument("--handle", required=True)
    p_admin.add_argument("--password", default=None)
    p_admin.add_argument("--display-name", default="管理员")

    p_invite = sub.add_parser("invite", help="发放邀请码")
    p_invite.add_argument("--count", type=int, default=1)
    p_invite.add_argument("--note", default=None)

    p_provider = sub.add_parser("provider", help="维护供应商端点白名单")
    p_provider.add_argument("--code", required=True)
    p_provider.add_argument("--name", required=True)
    p_provider.add_argument("--base-url", required=True)

    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except ApiError as exc:
        raise SystemExit(f"错误：{exc.message}")


if __name__ == "__main__":
    main()

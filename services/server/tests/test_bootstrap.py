"""Bootstrap credentials can be supplied without shell/argv interpolation."""

from argparse import Namespace

import pytest
from sqlalchemy import select

from aichat import bootstrap
from aichat.core.security import verify_password
from aichat.modules.identity.models import Account, HumanCredential


async def test_admin_password_from_environment_is_used_literally(ctx, monkeypatch):
    password = 'literal-$()-`quotes"-password'
    monkeypatch.setenv("TEST_BOOTSTRAP_PASSWORD", password)
    monkeypatch.setattr(bootstrap, "build_context", lambda: ctx)
    await bootstrap._run(Namespace(command="admin", handle="new-admin", password=None,
                                   password_env="TEST_BOOTSTRAP_PASSWORD", display_name="Admin"))
    async with ctx.db.session_factory() as session:
        account = await session.scalar(select(Account).where(Account.handle == "new-admin"))
        credential = await session.get(HumanCredential, account.id)
        assert account.is_admin
        assert verify_password(password, credential.password_hash)


async def test_admin_missing_password_environment_fails_without_prompt(ctx, monkeypatch):
    monkeypatch.delenv("TEST_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.setattr(bootstrap, "build_context", lambda: ctx)
    with pytest.raises(SystemExit, match="TEST_BOOTSTRAP_PASSWORD"):
        await bootstrap._run(Namespace(command="admin", handle="new-admin", password=None,
                                       password_env="TEST_BOOTSTRAP_PASSWORD", display_name="Admin"))

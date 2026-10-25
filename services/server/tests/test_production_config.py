"""Production must fail closed instead of using development credentials."""

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from aichat.core.config import Settings


@pytest.mark.parametrize("overrides", [
    {},
    {"jwt_secret": "a" * 32},
    {"jwt_secret": "short", "credential_master_key": Fernet.generate_key().decode()},
    {"jwt_secret": "a" * 32, "credential_master_key": "invalid"},
])
def test_production_rejects_missing_or_invalid_secrets(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, env="prod", **overrides)


def test_production_accepts_separate_valid_secrets():
    settings = Settings(_env_file=None, env="prod", jwt_secret="a" * 32,
                        credential_master_key=Fernet.generate_key().decode())
    assert settings.is_prod


def test_development_keeps_local_defaults():
    assert not Settings(_env_file=None).is_prod

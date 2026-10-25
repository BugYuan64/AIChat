"""密码哈希、JWT、令牌与凭据加密。"""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet

from aichat.core.config import Settings
from aichat.core.errors import auth_invalid

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def random_digits(n: int) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(n))


def random_code(alphabet: str, n: int) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(n))


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)  # 统一存 naive UTC


def create_access_token(
    settings: Settings,
    *,
    subject_type: str,  # human | connector
    subject_id: str,
    audience: str,
    expires_in: int,
    extra_claims: dict | None = None,
) -> tuple[str, datetime]:
    now = utcnow()
    payload = {
        "iss": "aichat",
        "sub": subject_id,
        "sub_typ": subject_type,
        "aud": audience,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": secrets.token_hex(8),
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, payload["exp"]


def decode_access_token(settings: Settings, token: str, audience: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience=audience, issuer="aichat")
    except jwt.ExpiredSignatureError:
        raise auth_invalid("访问令牌已过期")
    except jwt.InvalidTokenError:
        raise auth_invalid("访问令牌无效")


class CredentialCipher:
    """模型凭据透明加密。主密钥来自 settings；开发环境可从 jwt_secret 派生。"""

    def __init__(self, settings: Settings) -> None:
        if settings.credential_master_key:
            key = settings.credential_master_key.encode()
        else:
            key = base64.urlsafe_b64encode(hashlib.sha256(("cred:" + settings.jwt_secret).encode()).digest())
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()

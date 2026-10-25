"""连接器访问令牌缓存与刷新（契约 §7）。

POST /v1/connectors/access-tokens {refresh_credential} → {access_token, expires_in}。
访问令牌默认 15 分钟，过期前（留 60 秒余量）用 refresh_credential 换新；
401 SESSION_REVOKED / AUTH_INVALID 时提示必须重新配对。
"""

from __future__ import annotations

import time

import httpx

from .client import ApiError, REVOKED_CODES, post_json

# 过期前余量：提前刷新，避免临界过期
EXPIRY_MARGIN_SECONDS = 60.0
DEFAULT_EXPIRES_IN = 900.0  # 契约默认 15 分钟


class SessionRevokedError(Exception):
    """连接器凭据已撤销/失效，必须重新配对（不允许自动绕过）。"""


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


class TokenManager:
    """内存缓存访问令牌；跨请求复用同一个 httpx 客户端。"""

    def __init__(self, credentials: dict, server_base_url: str, http: httpx.AsyncClient) -> None:
        self._http = http
        self._base = server_base_url.rstrip("/")
        self._refresh_credential = str(credentials.get("refresh_credential") or "")
        if not self._refresh_credential:
            raise ValueError("凭据缺少 refresh_credential，请重新配对")
        # expires_in is relative to issuance, not process startup. Refresh saved
        # credentials once on startup instead of reviving an expired access token.
        self._access_token = None
        self._expires_at = 0.0

    async def get_access_token(self) -> str:
        """返回有效访问令牌；即将过期时先刷新。"""
        if self._access_token and time.monotonic() < self._expires_at - EXPIRY_MARGIN_SECONDS:
            return self._access_token
        return await self.refresh()

    async def refresh(self) -> str:
        """用 refresh_credential 换新访问令牌。"""
        try:
            data = await post_json(
                self._http,
                f"{self._base}/v1/connectors/access-tokens",
                json_body={"refresh_credential": self._refresh_credential},
            )
        except ApiError as err:
            if err.code in REVOKED_CODES:
                raise SessionRevokedError(
                    f"刷新访问令牌失败（{err.code}）：连接器凭据已失效或被撤销，需要重新配对。"
                ) from err
            raise
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise ApiError(code="PROTOCOL_ERROR", message="access-tokens 响应缺少 access_token")
        self._access_token = token
        self._expires_at = time.monotonic() + _to_float(
            data.get("expires_in"), default=DEFAULT_EXPIRES_IN
        )
        return self._access_token

    def invalidate(self) -> None:
        """连接被 401 拒绝时丢弃缓存，下轮强制刷新。"""
        self._access_token = None
        self._expires_at = 0.0

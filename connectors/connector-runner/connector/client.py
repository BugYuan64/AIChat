"""统一响应信封解析与 REST 错误处理。

契约（contracts/PROTOCOL.md §0）：
- 成功响应：{"request_id": "...", "data": {...}}
- 错误响应：{"request_id": "...", "error": {"code": "...", "message": "...", "retryable": bool, "retry_after_ms": int?}}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

# 需要按 retry_after_ms 退避的限流错误码（HTTP 429）
THROTTLE_CODES = frozenset({"RATE_LIMITED", "SLOW_DOWN"})

# 连接器凭据失效类错误码（HTTP 401）：必须重新配对，不允许自动绕过
REVOKED_CODES = frozenset({"SESSION_REVOKED", "AUTH_INVALID"})

# 配对相关错误码 → 统一映射为配对状态机状态
PAIRING_ERROR_STATUS = {
    "PAIRING_PENDING": "pending_user",
    "PAIRING_DENIED": "denied",
    "PAIRING_EXPIRED": "expired",
    "PAIRING_REVOKED": "revoked",
    "PAIRING_CONSUMED": "consumed",
}

# 配对终态（redeemed 表示已被兑换；本连接器轮询途中见到即为异常终态）
PAIRING_TERMINAL_STATUSES = frozenset(
    {"denied", "expired", "cancelled", "revoked", "consumed", "redeemed"}
)


@dataclass
class ApiError(Exception):
    """服务端按统一信封返回的错误。"""

    code: str
    message: str = ""
    retryable: bool = False
    retry_after_ms: int | None = None
    http_status: int | None = None

    def __str__(self) -> str:  # pragma: no cover - 展示用
        suffix = f"（HTTP {self.http_status}）" if self.http_status is not None else ""
        return f"[{self.code}] {self.message}{suffix}"


def parse_envelope(payload: Any, http_status: int | None = None) -> dict:
    """解析统一信封：成功返回 data 字典；错误信封抛出 ApiError。"""
    if not isinstance(payload, dict):
        raise ApiError(
            code="PROTOCOL_ERROR",
            message="响应不是 JSON 对象",
            http_status=http_status,
        )
    if "error" in payload:
        err = payload.get("error") or {}
        if not isinstance(err, dict):
            raise ApiError(
                code="PROTOCOL_ERROR",
                message="error 字段格式不合法",
                http_status=http_status,
            )
        raise ApiError(
            code=str(err.get("code") or "UNKNOWN"),
            message=str(err.get("message") or ""),
            retryable=bool(err.get("retryable", False)),
            retry_after_ms=err.get("retry_after_ms"),
            http_status=http_status,
        )
    if "data" not in payload:
        raise ApiError(
            code="PROTOCOL_ERROR",
            message="响应缺少 data 字段",
            http_status=http_status,
        )
    data = payload["data"]
    if not isinstance(data, dict):
        raise ApiError(
            code="PROTOCOL_ERROR",
            message="data 字段不是对象",
            http_status=http_status,
        )
    return data


def is_throttled(err: ApiError) -> bool:
    """是否为需要按 retry_after_ms 退避的限流错误。"""
    return err.code in THROTTLE_CODES


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    json_body: dict | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    """POST 并按统一信封解析；返回 data，错误抛 ApiError。"""
    resp = await client.post(url, json=json_body, headers=headers)
    try:
        payload = resp.json()
    except ValueError as exc:
        raise ApiError(
            code="PROTOCOL_ERROR",
            message=f"响应不是 JSON（HTTP {resp.status_code}）",
            http_status=resp.status_code,
        ) from exc
    return parse_envelope(payload, resp.status_code)

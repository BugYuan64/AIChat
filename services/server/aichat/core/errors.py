"""统一业务错误。所有模块抛 ApiError，由 envelope 层转为统一错误响应。"""

from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        retry_after_ms: int | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after_ms = retry_after_ms
        self.detail = detail


def validation_failed(message: str = "请求字段不合法") -> ApiError:
    return ApiError(400, "VALIDATION_FAILED", message)


def auth_invalid(message: str = "认证无效或已过期") -> ApiError:
    return ApiError(401, "AUTH_INVALID", message, retryable=False)


def session_revoked(message: str = "会话已撤销，请重新登录") -> ApiError:
    return ApiError(401, "SESSION_REVOKED", message)


def forbidden(message: str = "没有权限执行该操作") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def membership_revoked(message: str = "会话成员身份已失效") -> ApiError:
    return ApiError(403, "MEMBERSHIP_REVOKED", message)


def not_found(message: str = "对象不存在") -> ApiError:
    return ApiError(404, "NOT_FOUND", message)


def idempotency_conflict(message: str = "相同幂等键对应不同内容") -> ApiError:
    return ApiError(409, "IDEMPOTENCY_CONFLICT", message)


def version_conflict(message: str = "对象版本不匹配，请刷新后重试") -> ApiError:
    return ApiError(409, "VERSION_CONFLICT", message)


def stale_fence(message: str = "执行凭据已过期（fencing token 不匹配）") -> ApiError:
    return ApiError(409, "STALE_FENCE", message)


def delta_gap(next_chunk_index: int) -> ApiError:
    return ApiError(409, "DELTA_GAP", "增量缺片", detail={"next_chunk_index": next_chunk_index})


def cursor_expired() -> ApiError:
    return ApiError(410, "CURSOR_EXPIRED", "事件游标过期，需要全量重新同步")


def capability_unsupported(message: str = "当前接入方式不支持该能力") -> ApiError:
    return ApiError(422, "CAPABILITY_UNSUPPORTED", message)


def rate_limited(retry_after_ms: int = 1000, code: str = "RATE_LIMITED") -> ApiError:
    return ApiError(429, code, "请求过于频繁", retryable=True, retry_after_ms=retry_after_ms)


def temporarily_unavailable(message: str = "服务暂时不可用，请稍后重试") -> ApiError:
    return ApiError(503, "TEMPORARILY_UNAVAILABLE", message, retryable=True, retry_after_ms=1000)

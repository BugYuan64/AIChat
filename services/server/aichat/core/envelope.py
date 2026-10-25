"""统一响应信封：{"request_id", "data"} / {"request_id", "error"}。"""

import json
import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from aichat.core.errors import ApiError

logger = logging.getLogger("aichat")

WRAP_PREFIX = "/v1/"
WS_EXEMPT_PATHS = frozenset({"/v1/realtime", "/v1/connectors/realtime"})


def _request_id(request: Request) -> str:
    rid = request.headers.get("X-Request-Id")
    return rid or uuid4().hex


def error_body(request: Request, status: int, code: str, message: str, *, retryable: bool = False,
               retry_after_ms: int | None = None) -> dict:
    err: dict = {"code": code, "message": message, "retryable": retryable}
    if retry_after_ms is not None:
        err["retry_after_ms"] = retry_after_ms
    return {"request_id": _request_id(request), "error": err}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content=error_body(request, exc.status, exc.code, exc.message,
                               retryable=exc.retryable, retry_after_ms=exc.retry_after_ms),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content=error_body(request, 400, "VALIDATION_FAILED", "请求字段不合法"))

    @app.exception_handler(404)
    async def _http404(request: Request, exc) -> JSONResponse:
        path = request.url.path
        if not path.startswith(WRAP_PREFIX):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        return JSONResponse(status_code=404, content=error_body(request, 404, "NOT_FOUND", "对象不存在"))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s", request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=503,
            content=error_body(request, 503, "TEMPORARILY_UNAVAILABLE", "服务暂时不可用", retryable=True,
                               retry_after_ms=1000),
        )


class EnvelopeMiddleware(BaseHTTPMiddleware):
    """把 /v1 下的成功 JSON 响应包装为统一信封。"""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request.state.request_id = _request_id(request)
        response = await call_next(request)
        path = request.url.path
        if not path.startswith(WRAP_PREFIX) or path in WS_EXEMPT_PATHS:
            return response
        if response.status_code >= 400:
            return response  # 错误已由异常处理器包装
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        try:
            data = json.loads(body) if body else None
        except json.JSONDecodeError:
            return response
        wrapped = {"request_id": getattr(request.state, "request_id", uuid4().hex), "data": data}
        import starlette.responses as _resp

        return _resp.JSONResponse(status_code=response.status_code, content=wrapped,
                                  headers={k: v for k, v in response.headers.items()
                                           if k.lower() in ("x-request-id",)})

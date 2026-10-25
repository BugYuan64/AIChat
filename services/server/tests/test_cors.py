"""The separately hosted H5 may call API with Bearer auth; other origins may not."""

import pytest
from httpx import ASGITransport, AsyncClient

from aichat.app import create_app


@pytest.fixture()
def cors_app(settings):
    object.__setattr__(settings, "cors_origins", ["https://aichat.wsnbb.shop"])
    return create_app(settings)


async def test_h5_bearer_preflight_is_allowed(cors_app):
    async with AsyncClient(transport=ASGITransport(app=cors_app), base_url="https://api.aichat.wsnbb.shop") as client:
        response = await client.options("/v1/me", headers={
            "Origin": "https://aichat.wsnbb.shop",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        })
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://aichat.wsnbb.shop"
        assert "authorization" in response.headers["access-control-allow-headers"].lower()


async def test_disallowed_origin_cannot_pass_preflight(cors_app):
    async with AsyncClient(transport=ASGITransport(app=cors_app), base_url="https://api.aichat.wsnbb.shop") as client:
        response = await client.options("/v1/me", headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        })
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers


async def test_auth_error_response_keeps_cors_headers(cors_app):
    async with AsyncClient(transport=ASGITransport(app=cors_app), base_url="https://api.aichat.wsnbb.shop") as client:
        response = await client.get("/v1/me", headers={"Origin": "https://aichat.wsnbb.shop"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_INVALID"
        assert response.headers["access-control-allow-origin"] == "https://aichat.wsnbb.shop"

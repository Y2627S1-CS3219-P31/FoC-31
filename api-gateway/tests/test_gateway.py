from __future__ import annotations

import time
from unittest.mock import patch

import httpx
import pytest
from fastapi import Request
from jose import jwt

from app.config import settings
from app.services.exceptions import (
    InvalidTokenError,
    MissingBearerTokenError,
    RouteNotFoundError,
)
from app.services.gateway import GatewayService

gateway = GatewayService()


def _make_token(*, sub="user-1", role="client", exp_delta=3600) -> str:
    payload = {"sub": sub, "role": role, "exp": int(time.time()) + exp_delta}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/users/me",
        "headers": raw_headers,
        "query_string": b"",
    }

    async def _receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive=_receive)


def test_resolve_raises_for_unknown_route():
    with pytest.raises(RouteNotFoundError):
        gateway.resolve("/api/does-not-exist")


def test_resolve_returns_upstream_for_known_route():
    assert gateway.resolve("/api/users") == settings.user_service_url


async def test_authorize_public_route_needs_no_token():
    headers = await gateway.authorize("/api/users/login", _request())
    assert headers == {}


async def test_authorize_protected_route_without_token_raises():
    with pytest.raises(MissingBearerTokenError):
        await gateway.authorize("/api/users/me", _request())


async def test_authorize_protected_route_with_malformed_header_raises():
    with pytest.raises(MissingBearerTokenError):
        await gateway.authorize(
            "/api/users/me", _request({"authorization": "not-a-bearer-token"})
        )


async def test_authorize_protected_route_with_invalid_token_raises():
    with pytest.raises(InvalidTokenError):
        await gateway.authorize("/api/users/me", _request({"authorization": "Bearer garbage"}))


async def test_authorize_protected_route_with_valid_token_returns_trusted_headers():
    token = _make_token(sub="user-42", role="admin")
    headers = await gateway.authorize(
        "/api/users/me", _request({"authorization": f"Bearer {token}"})
    )
    assert headers == {"X-User-Id": "user-42", "X-User-Role": "admin"}


async def test_forward_strips_client_identity_headers_before_proxying():
    fake_response = httpx.Response(status_code=200, json={"ok": True})
    captured: dict[str, object] = {}

    async def _fake_request(self, **kwargs):
        captured.update(kwargs)
        return fake_response

    request = _request(
        {
            "authorization": "Bearer whatever",
            "x-user-id": "attacker-supplied",
            "x-user-role": "admin",
        }
    )
    with patch("httpx.AsyncClient.request", new=_fake_request):
        resp = await gateway.forward(
            upstream=settings.user_service_url,
            full_path="/api/users/me",
            request=request,
            injected_headers={"X-User-Id": "real-user", "X-User-Role": "client"},
        )

    assert resp.status_code == 200
    fwd_headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert captured["url"] == "/users/me"
    assert "authorization" not in fwd_headers
    assert fwd_headers["x-user-id"] == "real-user"
    assert fwd_headers["x-user-role"] == "client"

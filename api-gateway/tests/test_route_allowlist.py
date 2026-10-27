from __future__ import annotations

import re
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.config import settings
from app.exposed_routes import EXPOSED_ROUTES, ROUTE_TABLE
from app.main import app
from app.services.auth import PUBLIC_PREFIXES
from app.services.routing import is_canonical, resolve_upstream

client = TestClient(app)

_FRONTEND_API = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "api.ts"


def _auth(role: str = "client") -> dict[str, str]:
    token = jwt.encode(
        {"sub": "user-1", "role": role, "exp": int(time.time()) + 3600},
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _never_forwarded(*args, **kwargs):
    raise AssertionError("request must not reach a backend service")


# ── default deny ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "path"),
    [
        # Internal-only credit routes (order-service calls these directly).
        ("POST", "/api/credits/reservations"),
        ("POST", "/api/credits/reservations/r1/amend"),
        ("POST", "/api/credits/reservations/r1/transfer"),
        ("POST", "/api/credits/reservations/r1/release"),
        # Routes nobody added to the allowlist.
        ("GET", "/api/users/internal/debug"),
        ("GET", "/api/credits/observability/summary"),
        ("GET", "/api/users"),
        # Known paths with the wrong method.
        ("DELETE", "/api/users/me"),
        ("GET", "/api/users/login"),
        ("PUT", "/api/suppliers/s1"),
    ],
)
@pytest.mark.parametrize("role", ["client", "admin"])
def test_unlisted_requests_get_404_and_never_reach_a_backend(method, path, role):
    with patch.object(httpx.AsyncClient, "request", _never_forwarded):
        resp = client.request(method, path, headers=_auth(role), json={"courier_id": "friend"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


def test_unlisted_route_without_token_is_404_not_401():
    # The gateway does not reveal whether a private route exists.
    with patch.object(httpx.AsyncClient, "request", _never_forwarded):
        resp = client.post("/api/credits/reservations/r1/transfer")
    assert resp.status_code == 404


def test_exposed_route_is_forwarded_to_its_service():
    calls = []

    async def fake_request(self, *, method, url, **kwargs):
        calls.append((self.base_url, method, url))
        return httpx.Response(200, json={"available": 100})

    with patch.object(httpx.AsyncClient, "request", fake_request):
        resp = client.get("/api/credits/user-1/balance", headers=_auth())
    assert resp.status_code == 200
    assert [(m, u) for _, m, u in calls] == [("GET", "/credits/user-1/balance")]
    assert str(calls[0][0]).rstrip("/") == settings.credit_service_url.rstrip("/")


def test_head_is_allowed_where_get_is():
    assert resolve_upstream("HEAD", "/api/users/me") == settings.user_service_url


@pytest.mark.parametrize(
    "path",
    [
        "/api/suppliers/s1/deactivate/extra",  # extra segment
        "/api/credits/u1/balance/x",
        "/api/users/admin//role",  # empty {param}
    ],
)
def test_templates_match_whole_segments_only(path):
    assert resolve_upstream("GET", path) is None
    assert resolve_upstream("POST", path) is None
    assert resolve_upstream("PATCH", path) is None


# ── non-canonical paths ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        # httpx would resolve these to /credits/reservations/... upstream.
        "/api/credits/x/../reservations/r1/transfer",
        "/api/credits/./reservations/r1/transfer",
        "/api/credits//reservations/r1/transfer",
        # An exposed route must not be stretched to reach another one.
        "/api/users/login/../me",
        "/api/credits/u1/balance/../../reservations",
        "/api/users/me/",
        "/api/..",
        # A dot segment as a {param}: these DO match an exposed template, and
        # httpx would turn them into a different backend path.
        "/api/credits/../balance",
        "/api/orders/..",
        "/api/suppliers/./deactivate",
    ],
)
def test_non_canonical_paths_are_not_routed(path):
    assert not is_canonical(path)
    for method in ("GET", "POST", "PATCH", "DELETE"):
        assert resolve_upstream(method, path) is None


# ── allowlist consistency ────────────────────────────────────────────────────


def test_every_exposed_route_belongs_to_a_proxied_service():
    for method, template in EXPOSED_ROUTES:
        assert method in {"GET", "POST", "PUT", "PATCH", "DELETE"}, (method, template)
        assert any(
            template == prefix or template.startswith(prefix + "/") for prefix in ROUTE_TABLE
        ), template


@pytest.mark.parametrize(("method", "template"), EXPOSED_ROUTES)
def test_exposed_route_entries_are_well_formed(method, template):
    """Guards edits to app/exposed_routes.py. A malformed entry would never
    match (e.g. "{orderId}" is not a parameter, so it is matched literally)."""
    assert method == method.upper(), f"method must be upper case: {method!r}"
    assert template.startswith("/api/"), template
    assert not template.endswith("/"), f"no trailing slash: {template}"
    assert "//" not in template, template
    braces = re.findall(r"\{[^}]*\}", template)
    bad = [b for b in braces if not re.fullmatch(r"\{[a-z_]+\}", b)]
    assert not bad, f"parameters must look like {{snake_case}}: {bad} in {template}"
    leftover = re.sub(r"\{[a-z_]+\}", "", template)
    assert "{" not in leftover and "}" not in leftover, f"unbalanced braces in {template}"


def test_no_duplicate_exposed_routes():
    assert len(EXPOSED_ROUTES) == len(set(EXPOSED_ROUTES))


def test_every_unauthenticated_api_route_is_exposed():
    """A route made public in foc_shared must also be allowlisted here,
    otherwise it is public on paper but unreachable through the gateway."""
    templates = {template for _, template in EXPOSED_ROUTES}
    missing = [p for p in PUBLIC_PREFIXES if p.startswith("/api/") and p not in templates]
    assert not missing, f"public but not in EXPOSED_ROUTES: {missing}"


def _frontend_calls() -> list[tuple[str, str]]:
    source = _FRONTEND_API.read_text()
    calls = []
    for method, path in re.findall(
        r'request<[^>]*>\(\s*"(GET|POST|PUT|PATCH|DELETE)",\s*[`"](.*?)[`"]', source, re.S
    ):
        path = re.sub(r"\$\{buildQuery\(.*?\)\}", "", path, flags=re.S)  # query string
        path = re.sub(r"\$\{[^}]+\}", "x", path)  # path parameter
        calls.append((method, path))
    return calls


@pytest.mark.skipif(not _FRONTEND_API.exists(), reason="frontend sources not checked out")
def test_every_frontend_call_is_exposed():
    """Catches the allowlist's failure mode early: a frontend call to a route
    nobody exposed fails here instead of as a 404 in the browser."""
    calls = _frontend_calls()
    assert calls, "no API calls found; update the parser in this test"
    blocked = [f"{m} {p}" for m, p in calls if resolve_upstream(m, p) is None]
    assert not blocked, f"frontend calls routes the gateway does not expose: {blocked}"

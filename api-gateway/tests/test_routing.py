from __future__ import annotations

from app.config import settings
from app.services.routing import resolve_upstream


def test_resolve_exposed_route_returns_upstream():
    assert resolve_upstream("GET", "/api/users/me") == settings.user_service_url
    assert resolve_upstream("GET", "/api/suppliers/s1") == settings.supplier_service_url


def test_resolve_unknown_prefix_returns_none():
    assert resolve_upstream("GET", "/api/does-not-exist") is None


def test_resolve_does_not_match_partial_segment():
    # "/api/usersomething" must not match the "/api/users" prefix.
    assert resolve_upstream("GET", "/api/usersomething") is None


def test_bare_service_prefix_is_not_exposed():
    # Default deny: a service prefix alone is not a route.
    assert resolve_upstream("GET", "/api/users") is None

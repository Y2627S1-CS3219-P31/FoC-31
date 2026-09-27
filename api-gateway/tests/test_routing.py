from __future__ import annotations

from app.config import settings
from app.services.routing import resolve_upstream


def test_resolve_known_prefix_returns_upstream():
    assert resolve_upstream("/api/users") == settings.user_service_url
    assert resolve_upstream("/api/users/me") == settings.user_service_url


def test_resolve_unknown_prefix_returns_none():
    assert resolve_upstream("/api/does-not-exist") is None


def test_resolve_does_not_match_partial_segment():
    # "/api/usersomething" must not match the "/api/users" prefix.
    assert resolve_upstream("/api/usersomething") is None
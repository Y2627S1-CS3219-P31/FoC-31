from __future__ import annotations

from foc_shared.auth import HEADER_USER_ID, HEADER_USER_ROLE

PUBLIC_PREFIXES: tuple[str, ...] = ("/health", "/api/users/register", "/api/users/login")


def is_public(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PUBLIC_PREFIXES)


async def authenticate(token: str | None) -> tuple[str, str] | None:
    raise NotImplementedError


def build_trusted_headers(user_id: str, role: str) -> dict[str, str]:
    return {HEADER_USER_ID: user_id, HEADER_USER_ROLE: role}

from __future__ import annotations

from jose import JWTError, jwt

from app.config import settings
from foc_shared.auth import HEADER_USER_ID, HEADER_USER_ROLE, PUBLIC_ROUTE_PREFIXES, Role

PUBLIC_PREFIXES = PUBLIC_ROUTE_PREFIXES
JWT_ALGORITHM = "HS256"


def is_public(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in PUBLIC_PREFIXES)


async def authenticate(token: str | None) -> tuple[str, str] | None:
    """Verify bearer token and return (user_id, role)"""
    if not token or not settings.jwt_secret:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "role", "exp"]},
        )
    except JWTError:
        return None

    user_id = payload.get("sub")
    role = payload.get("role")
    valid_roles = {member.value for member in Role}
    if not isinstance(user_id, str) or not user_id:
        return None
    if not isinstance(role, str) or role not in valid_roles:
        return None
    return user_id, role


def build_trusted_headers(user_id: str, role: str) -> dict[str, str]:
    return {HEADER_USER_ID: user_id, HEADER_USER_ROLE: role}

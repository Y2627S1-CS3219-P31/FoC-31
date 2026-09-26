from __future__ import annotations

from jose import JWTError, jwt

from app.config import settings
from foc_shared.auth import HEADER_USER_ID, HEADER_USER_ROLE

# Must match the algorithm user-service uses to sign tokens on login.
JWT_ALGORITHM = "HS256"

async def authenticate(token: str | None) -> tuple[str, str] | None:
    """Verify a bearer token and return (user_id, role).

    Expects the JWT issued by user-service to carry the user id in the
    standard "sub" claim and the caller's role in a "role" claim, e.g.
    {"sub": "<user_id>", "role": "client", "exp": <unix_ts>}.

    Returns None for any missing, malformed, expired, or otherwise invalid
    token — the caller (main.py) turns that into a 401 response. This never
    raises so a bad token can't take down the proxy.
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None

    user_id = payload.get("sub")
    role = payload.get("role")
    if not user_id or not role:
        return None
    return str(user_id), str(role)


def build_trusted_headers(user_id: str, role: str) -> dict[str, str]:
    return {HEADER_USER_ID: user_id, HEADER_USER_ROLE: role}
from __future__ import annotations

import time

import bcrypt
from jose import jwt

from app.config import settings
from foc_shared.auth import Role

JWT_ALGORITHM = "HS256"
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    pw_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    pw_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(pw_bytes, password_hash.encode("utf-8"))


def issue_access_token(*, user_id: str, role: str) -> tuple[str, int]:
    """returns (token, ttl_seconds)"""
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    if role not in {member.value for member in Role}:
        raise ValueError("invalid user role")
    now = int(time.time())
    ttl = settings.jwt_access_token_ttl
    payload = {"sub": user_id, "role": role, "iat": now, "exp": now + ttl}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    return token, ttl
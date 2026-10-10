from __future__ import annotations

import time

from jose import jwt

from app.config import settings
from app.services.auth import authenticate

ALGORITHM = "HS256"


def _make_token(*, sub="user-1", role="client", exp_delta=3600, secret=None) -> str:
    payload = {"sub": sub, "role": role, "exp": int(time.time()) + exp_delta}
    return jwt.encode(payload, secret or settings.jwt_secret, algorithm=ALGORITHM)


async def test_authenticate_valid_token():
    token = _make_token()
    assert await authenticate(token) == ("user-1", "client")


async def test_authenticate_missing_token():
    assert await authenticate(None) is None


async def test_authenticate_empty_token():
    assert await authenticate("") is None


async def test_authenticate_expired_token():
    token = _make_token(exp_delta=-10)
    assert await authenticate(token) is None


async def test_authenticate_bad_signature():
    token = _make_token(secret="wrong-secret")
    assert await authenticate(token) is None


async def test_authenticate_missing_role_claim():
    token = jwt.encode({"sub": "user-1"}, settings.jwt_secret, algorithm=ALGORITHM)
    assert await authenticate(token) is None
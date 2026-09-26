from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

OTP_TTL = timedelta(minutes=5)

def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def expiry_from_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) + OTP_TTL
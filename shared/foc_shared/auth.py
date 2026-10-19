# AI-influenced: forgot-password changes made with Claude (Opus 5.5);
# see ai/usage-log.md.
from __future__ import annotations

from enum import Enum

HEADER_USER_ID = "X-User-Id"
HEADER_USER_ROLE = "X-User-Role"

PUBLIC_ROUTE_PREFIXES: tuple[str, ...] = (
    "/health",
    "/api/users/register",
    "/api/users/login",
    "/api/users/otp/verify",
    "/api/users/otp/resend",
    "/api/users/password/forgot",
    "/api/users/password/reset",
)


class Role(str, Enum):
    ADMIN = "admin"
    CLIENT = "client"
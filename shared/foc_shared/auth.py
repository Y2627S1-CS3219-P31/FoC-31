from __future__ import annotations

from enum import Enum

HEADER_USER_ID = "X-User-Id"
HEADER_USER_ROLE = "X-User-Role"


class Role(str, Enum):
    ADMIN = "admin"
    CLIENT = "client"

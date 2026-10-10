# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Shared FastAPI dependencies: caller identity + service wiring."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import UnauthorizedError
from app.services.credit_service import CreditService
from foc_shared.auth import HEADER_USER_ID, HEADER_USER_ROLE, Role


@dataclass(frozen=True)
class Identity:
    user_id: str
    role: str


def require_identity(
    x_user_id: str | None = Header(default=None, alias=HEADER_USER_ID),
    x_user_role: str | None = Header(default=None, alias=HEADER_USER_ROLE),
) -> Identity:
    """Credit N2.2: every credit operation requires an authenticated caller.

    Identity comes exclusively from the gateway-injected headers; roles are
    never client-asserted. A missing role degrades to `client`, never to
    `admin`."""
    if not x_user_id:
        raise UnauthorizedError("Authentication required.")
    # Only the exact string "admin" ever grants admin rights.
    role = x_user_role or Role.CLIENT.value
    return Identity(user_id=x_user_id, role=role)


async def get_credit_service(
    session: AsyncSession = Depends(get_session),
) -> CreditService:
    return CreditService(session)

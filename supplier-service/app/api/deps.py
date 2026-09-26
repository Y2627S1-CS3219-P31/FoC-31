from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import ForbiddenError, UnauthorizedError
from app.repositories.supplier_repo import SupplierRepository
from app.services.supplier_service import SupplierService
from foc_shared.auth import HEADER_USER_ID, HEADER_USER_ROLE, Role


def require_admin(
    x_user_id: str | None = Header(default=None, alias=HEADER_USER_ID),
    x_user_role: str | None = Header(default=None, alias=HEADER_USER_ROLE),
) -> str:
    if not x_user_id or not x_user_role:
        raise UnauthorizedError("Authentication required.")
    if x_user_role != Role.ADMIN.value:
        raise ForbiddenError("Admin role required.")
    return x_user_id


async def get_supplier_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[SupplierService, None]:
    yield SupplierService(SupplierRepository(session))

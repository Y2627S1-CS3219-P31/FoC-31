from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from foc_shared.auth import Role


def _list_conditions(*, q: str | None, status: str | None) -> list:
    conditions = []
    if q:
        like = f"%{q}%"
        conditions.append(or_(User.email.ilike(like), User.display_name.ilike(like)))
    if status == "active":
        conditions.append(User.is_suspended.is_(False))
    elif status == "suspended":
        conditions.append(User.is_suspended.is_(True))
    return conditions


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
        status: str | None = None,
    ) -> list[User]:
        conditions = _list_conditions(q=q, status=status)
        stmt = select(User).where(*conditions).order_by(User.created_at).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_all(self, *, q: str | None = None, status: str | None = None) -> int:
        conditions = _list_conditions(q=q, status=status)
        result = await self._session.execute(
            select(func.count()).select_from(User).where(*conditions)
        )
        return int(result.scalar_one())

    async def count_admins(self, *, exclude_suspended: bool = True) -> int:
        conditions = [User.role == Role.ADMIN.value]
        if exclude_suspended:
            conditions.append(User.is_suspended.is_(False))
        result = await self._session.execute(
            select(func.count()).select_from(User).where(*conditions)
        )
        return int(result.scalar_one())

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: str) -> User | None:
        return await self._session.get(User, user_id)

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user

    async def delete(self, user: User) -> None:
        await self._session.delete(user)
        await self._session.flush()

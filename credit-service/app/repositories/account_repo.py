# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import CreditAccount


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: str) -> CreditAccount | None:
        return await self._session.get(CreditAccount, user_id)

    async def get_for_update(self, user_id: str) -> CreditAccount | None:
        """Row-level lock (Credit N1.2.2): serializes concurrent operations on
        the same account so balance updates never lose writes."""
        result = await self._session.execute(
            select(CreditAccount).where(CreditAccount.user_id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def add(self, account: CreditAccount) -> CreditAccount:
        self._session.add(account)
        await self._session.flush()
        return account

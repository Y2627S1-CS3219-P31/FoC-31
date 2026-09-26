# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import CreditTransaction


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, transaction: CreditTransaction) -> CreditTransaction:
        self._session.add(transaction)
        await self._session.flush()
        return transaction

    async def list(
        self, user_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[CreditTransaction]:
        result = await self._session.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
            .order_by(CreditTransaction.created_at.desc(), CreditTransaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

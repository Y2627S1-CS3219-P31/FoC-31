# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_result import CreditTaskResult


class TaskResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, task_id: str) -> CreditTaskResult | None:
        return await self._session.get(CreditTaskResult, task_id)

    async def add(self, result: CreditTaskResult) -> CreditTaskResult:
        self._session.add(result)
        await self._session.flush()
        return result

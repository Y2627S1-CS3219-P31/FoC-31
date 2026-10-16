# AI-INFLUENCED: Order deletion outbox persistence implemented with Codex.
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_deletion_outbox import OrderDeletionOutbox


async def get_for_order(session: AsyncSession, order_id: str) -> OrderDeletionOutbox | None:
    return await session.scalar(
        select(OrderDeletionOutbox).where(OrderDeletionOutbox.order_id == order_id)
    )

# AI-INFLUENCED: Order update outbox persistence implemented with Codex.
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_update_outbox import PENDING, OrderUpdateOutbox


async def get_pending_for_order(session: AsyncSession, order_id: str) -> OrderUpdateOutbox | None:
    return await session.scalar(
        select(OrderUpdateOutbox).where(
            OrderUpdateOutbox.order_id == order_id,
            OrderUpdateOutbox.status == PENDING,
        )
    )

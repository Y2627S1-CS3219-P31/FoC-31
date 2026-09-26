# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orders import Order
from app.schemas.orders import OrderCreate


async def create_order(
    session: AsyncSession,
    order_data: OrderCreate,
    requester_id: str,
    status: str,
) -> Order:
    database_order = Order(
        **order_data.model_dump(),
        requester_id=requester_id,
        status=status,
    )

    session.add(database_order)
    try:
        await session.commit()
        await session.refresh(database_order)
    except Exception:
        await session.rollback()
        raise

    return database_order

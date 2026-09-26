# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
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


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    return await session.get(Order, order_id)


async def list_available_orders(
    session: AsyncSession,
    *,
    requester_id: str,
    status: str,
    now: datetime,
) -> list[Order]:
    statement = (
        select(Order)
        .where(
            Order.status == status,
            Order.courier_id.is_(None),
            Order.deadline > now,
            Order.requester_id != requester_id,
        )
        .order_by(Order.deadline.asc(), Order.id.asc())
    )
    result = await session.scalars(statement)
    return list(result.all())

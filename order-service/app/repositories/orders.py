# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orders import Order
from app.schemas.orders import OrderCreate


async def stage_order(
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
    await session.flush()
    return database_order


async def commit_order(session: AsyncSession) -> None:
    await session.commit()


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


async def list_orders_for_requester(
    session: AsyncSession,
    requester_id: str,
) -> list[Order]:
    statement = select(Order).where(Order.requester_id == requester_id).order_by(Order.id.asc())
    result = await session.scalars(statement)
    return list(result.all())


async def delete_order(session: AsyncSession, order: Order) -> None:
    await session.delete(order)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise

# AI-INFLUENCED: Sprint 1 order repository queries implemented with Codex.
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orders import OrderTable
from app.schemas.orders import OrderCreate
from app.services.lifecycle import OrderStatus


async def create_order(
    session: AsyncSession,
    new_order: OrderCreate,
    requester_id: str,
    order_id: str,
    reservation_id: str,
) -> OrderTable:
    # Make the order object
    order = OrderTable(
        order_id=order_id,
        name=new_order.name,
        details=new_order.details,
        reward=new_order.reward,
        deadline=new_order.deadline,
        supplier_id=new_order.supplier_id,
        requester_id=requester_id,
        reservation_id=reservation_id,
        pickup_location=new_order.pickup_location,
        delivery_location=new_order.delivery_location,
        status=OrderStatus.OPEN,
    )

    # Session operations
    session.add(order)
    await session.flush()
    await session.refresh(order)

    # Return the inserted row
    return order


async def list_available_orders(
    session: AsyncSession,
    requester_id: str,
) -> list[OrderTable]:
    statement = (
        select(OrderTable)
        .where(
            OrderTable.status == OrderStatus.OPEN,
            OrderTable.courier_id.is_(None),
            OrderTable.requester_id != requester_id,
        )
        .order_by(OrderTable.deadline.asc(), OrderTable.order_id.asc())
    )
    result = await session.scalars(statement)
    return list(result.all())


async def get_order(
    session: AsyncSession,
    order_id: str,
) -> OrderTable | None:
    return await session.get(OrderTable, order_id)


async def delete_order(session: AsyncSession, order: Order) -> None:
    await session.delete(order)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise

# AI-INFLUENCED: Sprint 1 order repository queries implemented with Codex.
from __future__ import annotations

from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_release_tasks import PENDING as RELEASE_PENDING
from app.models.order_release_tasks import OrderReleaseTask
from app.models.order_update_tasks import PENDING, OrderUpdateTask
from app.models.orders import OrderTable
from app.schemas.orders import OrderCreate, OrderUpdate
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
            ~select(OrderUpdateTask.task_id)
            .where(
                OrderUpdateTask.order_id == OrderTable.order_id,
                OrderUpdateTask.status == PENDING,
            )
            .exists(),
            ~select(OrderReleaseTask.task_id)
            .where(
                OrderReleaseTask.order_id == OrderTable.order_id,
                OrderReleaseTask.status == RELEASE_PENDING,
            )
            .exists(),
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


async def get_order_for_update(
    session: AsyncSession,
    order_id: str,
) -> OrderTable | None:
    statement = (
        select(OrderTable)
        .where(OrderTable.order_id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return await session.scalar(statement)


async def lock_courier_acceptance(session: AsyncSession, courier_id: str) -> None:
    # A transaction-scoped PostgreSQL lock also covers couriers with no orders yet.
    # Use a stable key shared by every process, not Python's randomized hash().
    key = int.from_bytes(
        sha256(f"order-acceptance:{courier_id}".encode()).digest()[:8], signed=True
    )
    await session.execute(select(func.pg_advisory_xact_lock(key)))


async def count_ongoing_for_courier(session: AsyncSession, courier_id: str) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(OrderTable)
        .where(
            OrderTable.courier_id == courier_id,
            OrderTable.status.in_(
                (OrderStatus.ACCEPTED, OrderStatus.PICKED_UP, OrderStatus.AWAITING_APPROVAL)
            ),
        )
    )
    return count or 0


async def assign_courier(session: AsyncSession, order: OrderTable, courier_id: str) -> None:
    order.courier_id = courier_id
    order.status = OrderStatus.ACCEPTED
    await session.flush()


async def set_status(session: AsyncSession, order: OrderTable, status: OrderStatus) -> None:
    order.status = status
    await session.flush()


async def delete_order(
    session: AsyncSession,
    order: OrderTable,
) -> None:
    await session.delete(order)
    await session.flush()


async def update_order(
    order: OrderTable, updated_order: OrderUpdate, session: AsyncSession
) -> OrderTable:
    changes = updated_order.model_dump(exclude_unset=True)

    for key, value in changes.items():
        setattr(order, key, value)

    await session.flush()
    return order

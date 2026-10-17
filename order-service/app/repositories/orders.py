# AI-INFLUENCED: Sprint 1 order repository queries implemented with Codex.
from __future__ import annotations

from datetime import datetime
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_release_tasks import PENDING as RELEASE_PENDING
from app.models.order_release_tasks import OrderReleaseTask
from app.models.order_update_tasks import PENDING, OrderUpdateTask
from app.models.orders import OrderTable
from app.schemas.orders import OrderCreate, OrderSortField, OrderUpdate, SortDirection
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
    supplier_ids: list[str] | None = None,
    min_reward: int | None = None,
    max_reward: int | None = None,
    sort_by: OrderSortField = OrderSortField.DEADLINE,
    sort_order: SortDirection = SortDirection.ASC,
) -> list[OrderTable]:
    filters = [
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
    ]
    if supplier_ids is not None:
        filters.append(OrderTable.supplier_id.in_(supplier_ids))
    if min_reward is not None:
        filters.append(OrderTable.reward >= min_reward)
    if max_reward is not None:
        filters.append(OrderTable.reward <= max_reward)

    sort_column = {
        OrderSortField.DEADLINE: OrderTable.deadline,
        OrderSortField.REWARD: OrderTable.reward,
    }[sort_by]
    sort_expression = sort_column.desc() if sort_order == SortDirection.DESC else sort_column.asc()

    statement = (
        select(OrderTable).where(*filters).order_by(sort_expression, OrderTable.order_id.asc())
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


async def get_due_orders_for_expiry(session: AsyncSession, limit: int) -> list[OrderTable]:
    statement = (
        select(OrderTable)
        .where(
            OrderTable.status == OrderStatus.OPEN,
            OrderTable.deadline <= func.current_timestamp(),
        )
        .order_by(OrderTable.deadline.asc(), OrderTable.order_id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    result = await session.scalars(statement)
    return list(result.all())


async def get_oldest_due_order(
    session: AsyncSession,
) -> tuple[str, datetime, datetime] | None:
    statement = (
        select(OrderTable.order_id, OrderTable.deadline, func.current_timestamp())
        .where(
            OrderTable.status == OrderStatus.OPEN,
            OrderTable.deadline <= func.current_timestamp(),
        )
        .order_by(OrderTable.deadline.asc(), OrderTable.order_id.asc())
        .limit(1)
    )
    row = (await session.execute(statement)).first()
    if row is None:
        return None
    return row[0], row[1], row[2]


async def set_statuses(
    session: AsyncSession, orders: list[OrderTable], status: OrderStatus
) -> None:
    for order in orders:
        order.status = status
    await session.flush()


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

# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orders import Order
from app.repositories import orders as order_repository
from app.schemas.orders import OrderCreate
from app.services.lifecycle import OrderStatus, assert_transition


class OrderNotFoundError(Exception):
    def __init__(self, order_id: int) -> None:
        self.order_id = order_id
        super().__init__(f"Order '{order_id}' was not found.")


class OrderAccessDeniedError(Exception):
    def __init__(self, order_id: int) -> None:
        self.order_id = order_id
        super().__init__(f"You do not have permission to access order '{order_id}'.")


class OrderStateConflictError(Exception):
    def __init__(self, order_id: int, message: str) -> None:
        self.order_id = order_id
        super().__init__(message)


async def create_order(
    session: AsyncSession,
    order_data: OrderCreate,
    requester_id: str,
) -> Order:
    return await order_repository.create_order(
        session,
        order_data,
        requester_id,
        OrderStatus.OPEN.value,
    )


async def list_available_orders(session: AsyncSession, requester_id: str) -> list[Order]:
    return await order_repository.list_available_orders(
        session,
        requester_id=requester_id,
        status=OrderStatus.OPEN.value,
        now=datetime.now(UTC),
    )


async def get_order_for_requester(
    session: AsyncSession,
    order_id: int,
    requester_id: str,
) -> Order:
    order = await order_repository.get_order(session, order_id)
    if order is None:
        raise OrderNotFoundError(order_id)
    if order.requester_id != requester_id:
        raise OrderAccessDeniedError(order_id)
    return order


async def delete_order_for_requester(
    session: AsyncSession,
    order_id: int,
    requester_id: str,
) -> None:
    order = await get_order_for_requester(session, order_id, requester_id)
    if order.courier_id is not None:
        raise OrderStateConflictError(
            order_id,
            "An order with an assigned courier cannot be deleted.",
        )

    try:
        current_status = OrderStatus(order.status)
        assert_transition(current_status, OrderStatus.CANCELLED)
    except ValueError as error:
        raise OrderStateConflictError(
            order_id,
            f"Order '{order_id}' cannot be deleted while its status is '{order.status}'.",
        ) from error

    await order_repository.delete_order(session, order)

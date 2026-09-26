# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orders import Order
from app.repositories import orders as order_repository
from app.schemas.orders import OrderCreate
from app.services.lifecycle import OrderStatus


class OrderNotFoundError(Exception):
    def __init__(self, order_id: int) -> None:
        self.order_id = order_id
        super().__init__(f"Order '{order_id}' was not found.")


class OrderAccessDeniedError(Exception):
    def __init__(self, order_id: int) -> None:
        self.order_id = order_id
        super().__init__(f"You do not have permission to access order '{order_id}'.")


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

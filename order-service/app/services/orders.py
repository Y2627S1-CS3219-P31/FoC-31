# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orders import Order
from app.repositories import orders as order_repository
from app.schemas.orders import OrderCreate
from app.services.lifecycle import OrderStatus


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

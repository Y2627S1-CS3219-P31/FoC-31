# AI-INFLUENCED: Sprint 1 Order Service workflows implemented with Codex.
from __future__ import annotations

from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orders import OrderTable
from app.repositories import orders as order_repository
from app.schemas.orders import OrderCreate
from app.services.clients.credit.error import CreditClientError
from app.services.clients.credit.release_credits import release_credits
from app.services.clients.credit.reserve_credits import reserve_credits
from app.services.clients.errors import RemoteServiceError
from app.services.clients.supplier.error import SupplierInactiveError
from app.services.clients.supplier.get_supplier import get_supplier
from app.services.errors import (
    OrderAccessDeniedError,
    OrderDeletionError,
    OrderNotFoundError,
    OrderPersistenceError,
    OrderRetrievalError,
    OrderStateConflictError,
)
from app.services.lifecycle import OrderStatus


async def create_order(
    new_order: OrderCreate,
    requester_id: str,
    session: AsyncSession,
) -> OrderTable:
    # Get the supplier
    supplier_id = new_order.supplier_id
    supplier = await get_supplier(supplier_id)

    # Handle inactive supplier
    if not supplier.active:
        raise SupplierInactiveError(supplier_id)

    # Generate the order id
    order_id = str(uuid4())

    # Reserve credits
    reward = new_order.reward
    reservation = await reserve_credits(
        reward,
        requester_id,
        order_id,
    )

    # Start and commit the session
    try:
        async with session.begin():
            # Call the repository action
            created_order = await order_repository.create_order(
                session,
                new_order,
                requester_id,
                order_id,
                reservation.id,
            )
    except SQLAlchemyError as exc:
        await release_credits(
            reservation_id=reservation.id,
            requester_id=requester_id,
        )
        raise OrderPersistenceError(order_id) from exc

    return created_order


async def list_available_orders(
    session: AsyncSession,
    requester_id: str,
) -> list[OrderTable]:
    try:
        return await order_repository.list_available_orders(session, requester_id)
    except SQLAlchemyError as exc:
        raise OrderRetrievalError() from exc


async def get_order_for_requester(
    session: AsyncSession,
    order_id: str,
    requester_id: str,
) -> OrderTable:
    try:
        order = await order_repository.get_order(session, order_id)
    except SQLAlchemyError as exc:
        raise OrderRetrievalError(order_id) from exc

    if order is None:
        raise OrderNotFoundError(order_id)
    if order.requester_id != requester_id:
        raise OrderAccessDeniedError(order_id)
    return order


async def delete_order_for_requester(
    session: AsyncSession,
    order_id: str,
    requester_id: str,
) -> None:
    try:
        async with session.begin():
            order = await order_repository.get_order_for_update(session, order_id)
            if order is None:
                raise OrderNotFoundError(order_id)
            if order.requester_id != requester_id:
                raise OrderAccessDeniedError(order_id)

            status = OrderStatus(order.status)
            if status != OrderStatus.OPEN or order.courier_id is not None:
                raise OrderStateConflictError(
                    order_id,
                    "Only an open order without an assigned courier can be deleted.",
                )

            await release_credits(
                reservation_id=order.reservation_id,
                requester_id=requester_id,
            )
            await order_repository.delete_order(session, order)
    except (
        CreditClientError,
        OrderAccessDeniedError,
        OrderNotFoundError,
        OrderStateConflictError,
        RemoteServiceError,
    ):
        raise
    except SQLAlchemyError as exc:
        raise OrderDeletionError(order_id) from exc

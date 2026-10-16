# AI-INFLUENCED: Sprint 1 Order Service workflows implemented with Codex.
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orders import OrderTable
from app.repositories import order_deletion_outbox as deletion_outbox_repository
from app.repositories import order_event_outbox as event_outbox_repository
from app.repositories import order_update_outbox as update_outbox_repository
from app.repositories import orders as order_repository
from app.schemas.orders import OrderCreate, OrderUpdate
from app.services.client_manager import get_credit_client
from app.services.clients.credit.error import CreditClientError
from app.services.clients.errors import RemoteServiceError
from app.services.clients.supplier.error import SupplierInactiveError
from app.services.clients.supplier.get_supplier import get_supplier
from app.services.errors import (
    OrderAcceptanceError,
    OrderAccessDeniedError,
    OrderDeletionError,
    OrderNotEditableError,
    OrderNotFoundError,
    OrderPersistenceError,
    OrderRetrievalError,
    OrderStateConflictError,
)
from app.services.lifecycle import OrderStatus, assert_transition
from foc_shared.events import OrderEvent, OrderEventType


async def accept_order(session: AsyncSession, order_id: str, courier_id: str) -> OrderTable:
    try:
        async with session.begin():
            # Serialize this courier's count/check/write across different orders.
            await order_repository.lock_courier_acceptance(session, courier_id)
            order = await order_repository.get_order_for_update(session, order_id)
            if order is None:
                raise OrderNotFoundError(order_id)
            if order.requester_id == courier_id:
                raise OrderStateConflictError(order_id, "You cannot accept your own order.")
            if order.courier_id is not None:
                raise OrderStateConflictError(order_id, "Order already has an assigned courier.")
            if order.status != OrderStatus.OPEN:
                raise OrderStateConflictError(order_id, "Order is not available.")
            if order.deadline <= datetime.now(UTC):
                raise OrderStateConflictError(order_id, "Order has expired.")

            # Published amendments remain pending until their result is applied.
            if await update_outbox_repository.get_pending_for_order(session, order_id):
                raise OrderStateConflictError(order_id, "Order update is still pending.")
            if await deletion_outbox_repository.get_for_order(session, order_id):
                raise OrderStateConflictError(order_id, "Order is unavailable due to deletion.")
            if await order_repository.count_ongoing_for_courier(session, courier_id) >= 3:
                raise OrderStateConflictError(order_id, "You already have 3 ongoing orders.")

            assert_transition(OrderStatus(order.status), OrderStatus.ACCEPTED)
            await order_repository.assign_courier(session, order, courier_id)
            # Assignment and its event must either both commit or both roll back.
            await event_outbox_repository.create_event(
                session,
                OrderEvent(
                    event_type=OrderEventType.ORDER_ACCEPTED,
                    order_id=order.order_id,
                    requester_id=order.requester_id,
                    courier_id=courier_id,
                    timestamp=datetime.now(UTC),
                ),
            )
        return order
    except SQLAlchemyError as exc:
        raise OrderAcceptanceError(order_id) from exc


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
    reservation = await get_credit_client().reserve_credits(
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
        await get_credit_client().release_credits(
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

            await order_repository.delete_order(session, order)

        await get_credit_client().release_credits(
            reservation_id=order.reservation_id,
            requester_id=requester_id,
        )
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


async def update_order(
    order_id: str,
    updated_order: OrderUpdate,
    requester_id: str,
    session: AsyncSession
) -> OrderTable:
    should_amend_credit = False

    async with session.begin():
        # Get the order's details first for validation checks
        # No try-except because the get_order_for_requester already raises them
        order = await get_order_for_requester(
            session=session,
            order_id=order_id,
            requester_id=requester_id
        )

        if order.reward != updated_order.reward:
            should_amend_credit = True

        # Reject update requests for orders that have been accepted by a courier
        if (order.courier_id is not None or order.status is not OrderStatus.OPEN):
            raise OrderNotEditableError(order_id)

        # Call the order repository service with the new order information
        await order_repository.update_order(
            order=order,
            updated_order=updated_order,
            session=session
        )

    # Call the credit service to amend the existing reservation
    # No try-except because the amend_credits function already raises them
    if (should_amend_credit):
        await get_credit_client().amend_credits(
            reservation_id=order.reservation_id,
            requester_id=requester_id,
            amount=updated_order.reward
        )

    return order

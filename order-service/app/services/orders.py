# AI-INFLUENCED: Sprint 1 Order Service workflows implemented with Codex.
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_approval_tasks import OrderApprovalTask
from app.models.order_release_tasks import OrderReleaseTask, ReleaseAction
from app.models.order_update_tasks import OrderUpdateTask
from app.models.orders import OrderTable
from app.repositories import order_approval_tasks as approval_tasks
from app.repositories import order_event_outbox as event_outbox_repository
from app.repositories import order_release_tasks as release_tasks
from app.repositories import order_requests as request_repository
from app.repositories import order_update_tasks as update_tasks
from app.repositories import orders as order_repository
from app.schemas.order_action_events import OrderActionEvent, OrderActionEventType
from app.schemas.order_approval_events import OrderApprovalRequestedEvent
from app.schemas.order_update_events import OrderUpdateRequestedEvent
from app.schemas.orders import (
    OrderCreate,
    OrderResponse,
    OrderSortField,
    OrderUpdate,
    SortDirection,
)
from app.services import proof_photo
from app.services.client_manager import get_credit_client, get_supplier_client
from app.services.clients.supplier.error import SupplierInactiveError
from app.services.clients.supplier.get_supplier import get_supplier
from app.services.errors import (
    OrderAcceptanceError,
    OrderAccessDeniedError,
    OrderApprovalError,
    OrderCancellationError,
    OrderDeletionError,
    OrderDeliveryError,
    OrderNotEditableError,
    OrderNotFoundError,
    OrderPersistenceError,
    OrderPickupError,
    OrderRetrievalError,
    OrderStateConflictError,
    OrderWithdrawalError,
)
from app.services.lifecycle import OrderStatus, assert_transition
from foc_shared.events import OrderEvent, OrderEventType

ORDER_ACTION_EVENT_TYPES: dict[ReleaseAction, OrderActionEventType] = {
    ReleaseAction.DELETE: "OrderDeletionRequested",
    ReleaseAction.CANCEL: "OrderCancellationRequested",
}
logger = logging.getLogger(__name__)


def _build_order_action_event(task: OrderReleaseTask) -> OrderActionEvent:
    return OrderActionEvent(
        event_type=ORDER_ACTION_EVENT_TYPES[ReleaseAction(task.action)],
        task_id=task.task_id,
        order_id=task.order_id,
        reservation_id=task.reservation_id,
        requester_id=task.requester_id,
        timestamp=task.created_at,
        reason=task.reason,
    )


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
            if await update_tasks.get_pending_for_order(session, order_id):
                raise OrderStateConflictError(order_id, "Order update is still pending.")
            if await release_tasks.get_for_order(session, order_id):
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


async def pickup_order(session: AsyncSession, order_id: str, courier_id: str) -> OrderTable:
    try:
        async with session.begin():
            order = await order_repository.get_order_for_update(session, order_id)
            if order is None:
                raise OrderNotFoundError(order_id)
            if order.courier_id != courier_id:
                raise OrderAccessDeniedError(order_id)
            if order.status != OrderStatus.ACCEPTED:
                raise OrderStateConflictError(order_id, "Only an accepted order can be picked up.")
            if await release_tasks.get_for_order(session, order_id):
                raise OrderStateConflictError(order_id, "A terminal action is pending.")

            assert_transition(OrderStatus(order.status), OrderStatus.PICKED_UP)
            await order_repository.set_status(session, order, OrderStatus.PICKED_UP)
            await event_outbox_repository.create_event(
                session,
                OrderEvent(
                    event_type=OrderEventType.ORDER_PICKED_UP,
                    order_id=order.order_id,
                    requester_id=order.requester_id,
                    courier_id=courier_id,
                    timestamp=datetime.now(UTC),
                ),
            )
        return order
    except SQLAlchemyError as exc:
        raise OrderPickupError(order_id) from exc


async def withdraw_order(
    session: AsyncSession, order_id: str, courier_id: str, request_id: str
) -> OrderResponse:
    try:
        async with session.begin():
            await request_repository.lock_request_id(session, request_id)
            existing = await request_repository.get_request(session, request_id)
            if existing is not None:
                if (
                    existing.action != "withdraw"
                    or existing.order_id != order_id
                    or existing.actor_id != courier_id
                ):
                    raise OrderStateConflictError(
                        order_id, "Idempotency key was used for another request."
                    )
                return OrderResponse.model_validate(existing.response)

            order = await order_repository.get_order_for_update(session, order_id)
            if order is None:
                raise OrderNotFoundError(order_id)
            if order.courier_id != courier_id:
                raise OrderAccessDeniedError(order_id)
            if order.status != OrderStatus.ACCEPTED:
                raise OrderStateConflictError(
                    order_id, "Only an accepted order can be withdrawn from."
                )
            if await release_tasks.get_for_order(session, order_id):
                raise OrderStateConflictError(order_id, "A terminal action is pending.")

            assert_transition(OrderStatus(order.status), OrderStatus.OPEN)
            await order_repository.unassign_courier(session, order)
            response = OrderResponse.model_validate(order)
            await request_repository.save_request(
                session,
                request_id=request_id,
                action="withdraw",
                order_id=order_id,
                actor_id=courier_id,
                response=response.model_dump(mode="json"),
            )
            await event_outbox_repository.create_event(
                session,
                OrderEvent(
                    event_type=OrderEventType.COURIER_WITHDRAWN,
                    order_id=order_id,
                    requester_id=order.requester_id,
                    courier_id=courier_id,
                    timestamp=datetime.now(UTC),
                ),
            )
        return response
    except SQLAlchemyError as exc:
        raise OrderWithdrawalError(order_id) from exc


async def deliver_order(
    session: AsyncSession, order_id: str, courier_id: str, photo: proof_photo.Photo
) -> OrderTable:
    photo_key = None
    committed = False
    try:
        async with session.begin():
            order = await order_repository.get_order_for_update(session, order_id)
            if order is None:
                raise OrderNotFoundError(order_id)
            if order.courier_id != courier_id:
                raise OrderAccessDeniedError(order_id)

            current_status = OrderStatus(order.status)
            if current_status != OrderStatus.PICKED_UP:
                raise OrderStateConflictError(
                    order_id, "Only a picked-up order can be marked as delivered."
                )

            assert_transition(current_status, OrderStatus.AWAITING_APPROVAL)
            photo_key = await proof_photo.upload(order_id, photo)
            delivered_at = datetime.now(UTC)
            order.proof_of_delivery_photo_key = photo_key
            order.awaiting_approval_at = delivered_at
            await order_repository.set_status(session, order, OrderStatus.AWAITING_APPROVAL)
            await event_outbox_repository.create_event(
                session,
                OrderEvent(
                    event_type=OrderEventType.ORDER_DELIVERED,
                    order_id=order.order_id,
                    requester_id=order.requester_id,
                    courier_id=order.courier_id,
                    timestamp=delivered_at,
                ),
            )
        committed = True
        return order
    except SQLAlchemyError as exc:
        raise OrderDeliveryError(order_id) from exc
    finally:
        if photo_key and not committed:
            try:
                await proof_photo.delete(photo_key)
            except Exception:
                logger.exception(
                    "Could not remove unreferenced delivery photo for order %s", order_id
                )


async def approve_order_for_requester(
    session: AsyncSession, order_id: str, requester_id: str
) -> OrderApprovalTask:
    try:
        async with session.begin():
            order = await order_repository.get_order_for_update(session, order_id)
            if order is None:
                raise OrderNotFoundError(order_id)
            if order.requester_id != requester_id:
                raise OrderAccessDeniedError(order_id)
            if order.status != OrderStatus.AWAITING_APPROVAL:
                raise OrderStateConflictError(
                    order_id, "Only a delivered order awaiting approval can be approved."
                )
            if order.courier_id is None:
                raise OrderStateConflictError(order_id, "The order has no assigned courier.")

            existing = await approval_tasks.get_pending_for_order(session, order_id)
            if existing is not None:
                return existing

            task = await approval_tasks.create_task(
                session,
                order_id=order.order_id,
                reservation_id=order.reservation_id,
                requester_id=order.requester_id,
                courier_id=order.courier_id,
            )
            await event_outbox_repository.create_event(
                session,
                OrderApprovalRequestedEvent(
                    task_id=task.task_id,
                    order_id=task.order_id,
                    reservation_id=task.reservation_id,
                    requester_id=task.requester_id,
                    courier_id=task.courier_id,
                    timestamp=task.created_at,
                ),
            )
            return task
    except (OrderAccessDeniedError, OrderNotFoundError, OrderStateConflictError):
        raise
    except SQLAlchemyError as exc:
        raise OrderApprovalError(order_id) from exc


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
    categories: list[str] | None = None,
    min_reward: int | None = None,
    max_reward: int | None = None,
    sort_by: OrderSortField = OrderSortField.DEADLINE,
    sort_order: SortDirection = SortDirection.ASC,
) -> list[OrderTable]:
    supplier_ids = None
    if categories:
        supplier_ids = await get_supplier_client().get_supplier_ids_by_categories(
            list(dict.fromkeys(categories))
        )
        if not supplier_ids:
            return []

    try:
        return await order_repository.list_available_orders(
            session,
            requester_id,
            supplier_ids=supplier_ids,
            min_reward=min_reward,
            max_reward=max_reward,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except SQLAlchemyError as exc:
        raise OrderRetrievalError() from exc


async def list_assigned_orders(session: AsyncSession, courier_id: str) -> list[OrderTable]:
    try:
        return await order_repository.list_assigned_orders(session, courier_id)
    except SQLAlchemyError as exc:
        raise OrderRetrievalError() from exc


async def list_requested_ongoing_orders(
    session: AsyncSession, requester_id: str
) -> list[OrderTable]:
    try:
        return await order_repository.list_requested_ongoing_orders(session, requester_id)
    except SQLAlchemyError as exc:
        raise OrderRetrievalError() from exc


async def list_requested_completed_orders(
    session: AsyncSession, requester_id: str
) -> list[OrderTable]:
    try:
        return await order_repository.list_requested_completed_orders(session, requester_id)
    except SQLAlchemyError as exc:
        raise OrderRetrievalError() from exc


async def list_assigned_completed_orders(
    session: AsyncSession, courier_id: str
) -> list[OrderTable]:
    try:
        return await order_repository.list_assigned_completed_orders(session, courier_id)
    except SQLAlchemyError as exc:
        raise OrderRetrievalError() from exc


async def get_order_for_participant(
    session: AsyncSession,
    order_id: str,
    user_id: str,
) -> tuple[OrderTable, proof_photo.Photo | None]:
    try:
        order = await order_repository.get_order(session, order_id)
    except SQLAlchemyError as exc:
        raise OrderRetrievalError(order_id) from exc

    if order is None:
        raise OrderNotFoundError(order_id)
    is_courier = bool(order.courier_id) and order.courier_id == user_id
    if order.requester_id != user_id and not is_courier:
        raise OrderAccessDeniedError(order_id)
    photo = None
    if order.proof_of_delivery_photo_key:
        photo = await proof_photo.get(order.proof_of_delivery_photo_key)
    return order, photo


async def get_deletion_for_requester(
    session: AsyncSession, task_id: str, requester_id: str
) -> OrderReleaseTask:
    try:
        task = await release_tasks.get_task(session, task_id)
    except SQLAlchemyError as exc:
        raise OrderRetrievalError() from exc
    if task is None or task.action != ReleaseAction.DELETE:
        raise OrderNotFoundError(task_id)
    if task.requester_id != requester_id:
        raise OrderAccessDeniedError(task.order_id)
    return task


async def delete_order_for_requester(
    session: AsyncSession,
    order_id: str,
    requester_id: str,
) -> OrderReleaseTask:
    try:
        async with session.begin():
            order = await order_repository.get_order_for_update(session, order_id)
            if order is None:
                raise OrderNotFoundError(order_id)
            if order.requester_id != requester_id:
                raise OrderAccessDeniedError(order_id)

            existing = await release_tasks.get_for_order(session, order_id)
            if existing is not None:
                if existing.action == ReleaseAction.DELETE.value:
                    return existing
                raise OrderStateConflictError(
                    order_id, "A different terminal action is already pending."
                )

            status = OrderStatus(order.status)
            if status != OrderStatus.OPEN or order.courier_id is not None:
                raise OrderStateConflictError(
                    order_id,
                    "Only an open order without an assigned courier can be deleted.",
                )

            if await update_tasks.get_pending_for_order(session, order_id):
                raise OrderStateConflictError(
                    order_id, "This order has an update in progress. Try deleting it later."
                )

            task = await release_tasks.create_task(
                session,
                order_id=order_id,
                requester_id=requester_id,
                reservation_id=order.reservation_id,
                action=ReleaseAction.DELETE,
            )
            await event_outbox_repository.create_event(session, _build_order_action_event(task))
            return task
    except (
        OrderAccessDeniedError,
        OrderNotFoundError,
        OrderStateConflictError,
    ):
        raise
    except SQLAlchemyError as exc:
        raise OrderDeletionError(order_id) from exc


async def cancel_order_for_requester(
    session: AsyncSession,
    order_id: str,
    requester_id: str,
    reason: str,
) -> OrderReleaseTask:
    try:
        async with session.begin():
            order = await order_repository.get_order_for_update(session, order_id)
            if order is None:
                raise OrderNotFoundError(order_id)
            if order.requester_id != requester_id:
                raise OrderAccessDeniedError(order_id)

            existing = await release_tasks.get_for_order(session, order_id)
            if existing is not None:
                if existing.action != ReleaseAction.CANCEL.value:
                    raise OrderStateConflictError(
                        order_id, "A different terminal action is already pending."
                    )
                return existing

            current_status = OrderStatus(order.status)
            if current_status not in (OrderStatus.OPEN, OrderStatus.ACCEPTED):
                raise OrderStateConflictError(
                    order_id, "Only an open or accepted order can be cancelled."
                )

            if await update_tasks.get_pending_for_order(session, order_id):
                raise OrderStateConflictError(
                    order_id, "This order has an update in progress. Try cancelling it later."
                )

            assert_transition(current_status, OrderStatus.CANCELLED)
            task = await release_tasks.create_task(
                session,
                order_id=order_id,
                requester_id=requester_id,
                reservation_id=order.reservation_id,
                action=ReleaseAction.CANCEL,
                reason=reason,
            )
            await event_outbox_repository.create_event(session, _build_order_action_event(task))
            return task
    except (
        OrderAccessDeniedError,
        OrderNotFoundError,
        OrderStateConflictError,
    ):
        raise
    except SQLAlchemyError as exc:
        raise OrderCancellationError(order_id) from exc


async def update_order(
    order_id: str,
    updated_order: OrderUpdate,
    requester_id: str,
    session: AsyncSession,
) -> OrderUpdateTask:
    async with session.begin():
        order = await order_repository.get_order_for_update(session, order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        if order.requester_id != requester_id:
            raise OrderAccessDeniedError(order_id)
        if order.courier_id is not None or order.status != OrderStatus.OPEN:
            raise OrderNotEditableError(order_id)
        if await release_tasks.get_for_order(session, order_id):
            raise OrderStateConflictError(order_id, "This order has a pending terminal action.")

        proposed_order = updated_order.model_dump(mode="json")
        pending = await update_tasks.get_pending_for_order(session, order_id)
        if pending is not None:
            if pending.proposed_order != proposed_order:
                raise OrderStateConflictError(
                    order_id, "This order already has a different update in progress."
                )
            return pending
        task = await update_tasks.create_task(
            session,
            order_id=order_id,
            requester_id=requester_id,
            reservation_id=order.reservation_id,
            proposed_order=proposed_order,
        )
        await event_outbox_repository.create_event(
            session,
            OrderUpdateRequestedEvent(
                task_id=task.task_id,
                order_id=task.order_id,
                reservation_id=task.reservation_id,
                requester_id=task.requester_id,
                reward=task.proposed_order["reward"],
                timestamp=task.created_at,
            ),
        )
        return task


async def get_update_for_requester(
    session: AsyncSession, task_id: str, requester_id: str
) -> OrderUpdateTask:
    try:
        task = await update_tasks.get_task(session, task_id)
    except SQLAlchemyError as exc:
        raise OrderRetrievalError() from exc
    if task is None:
        raise OrderNotFoundError(task_id)
    if task.requester_id != requester_id:
        raise OrderAccessDeniedError(task.order_id)
    return task

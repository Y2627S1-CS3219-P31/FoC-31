# AI-INFLUENCED: Retriable order lifecycle event delivery implemented with Codex.
from __future__ import annotations

import asyncio
import logging

from app.db import SessionLocal
from app.repositories import order_event_outbox as event_repository
from app.schemas.order_action_events import (
    OrderActionEvent,
    OrderCancellationFailedEvent,
    OrderDeletedEvent,
    OrderDeletionFailedEvent,
    OrderLocalOutcomeEvent,
)
from app.schemas.order_approval_events import (
    OrderApprovalEvent,
    OrderApprovalFailedEvent,
    OrderApprovalRequestedEvent,
    OrderApprovedEvent,
)
from app.schemas.order_update_events import (
    OrderUpdatedEvent,
    OrderUpdateFailedEvent,
    OrderUpdateOutcomeEvent,
    OrderUpdateRequestedEvent,
)
from app.services.events import publish_order_event
from foc_shared.events import OrderEvent

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 5


LOCAL_OUTCOME_TYPES: dict[str, type[OrderLocalOutcomeEvent]] = {
    "OrderCancellationFailed": OrderCancellationFailedEvent,
    "OrderDeleted": OrderDeletedEvent,
    "OrderDeletionFailed": OrderDeletionFailedEvent,
}
ACTION_EVENT_TYPES = {
    "OrderDeletionRequested",
    "OrderCancellationRequested",
    "OrderExpiryRequested",
}
UPDATE_OUTCOME_TYPES: dict[str, type[OrderUpdateOutcomeEvent]] = {
    "OrderUpdated": OrderUpdatedEvent,
    "OrderUpdateFailed": OrderUpdateFailedEvent,
}
APPROVAL_OUTCOME_TYPES: dict[str, type[OrderApprovalEvent]] = {
    "OrderApprovalFailed": OrderApprovalFailedEvent,
    "OrderApproved": OrderApprovedEvent,
}


def _parse_event(
    payload: dict,
) -> (
    OrderEvent
    | OrderActionEvent
    | OrderLocalOutcomeEvent
    | OrderUpdateRequestedEvent
    | OrderUpdateOutcomeEvent
    | OrderApprovalEvent
):
    event_type = payload.get("event_type")
    if event_type in ACTION_EVENT_TYPES:
        return OrderActionEvent.model_validate(payload)
    if event_type == "OrderUpdateRequested":
        return OrderUpdateRequestedEvent.model_validate(payload)
    if event_type == "OrderApprovalRequested":
        return OrderApprovalRequestedEvent.model_validate(payload)
    event_model = (
        LOCAL_OUTCOME_TYPES.get(event_type)
        or UPDATE_OUTCOME_TYPES.get(event_type)
        or APPROVAL_OUTCOME_TYPES.get(event_type)
    )
    if event_model is not None:
        return event_model.model_validate(payload)
    return OrderEvent.model_validate(payload)


async def publish_pending_events() -> None:
    async with SessionLocal() as session:
        event_ids = await event_repository.list_pending_event_ids(session)

    for event_id in event_ids:
        async with SessionLocal() as session, session.begin():
            # Skip rows another worker is publishing; hold only this event's lock.
            task = await event_repository.get_pending_for_update(session, event_id)
            if task is None:
                continue
            try:
                async with asyncio.timeout(10):
                    await publish_order_event(_parse_event(task.payload), event_id=event_id)
            except Exception as exc:
                logger.warning(
                    "Could not publish order event", extra={"event_id": event_id}, exc_info=True
                )
                error = str(exc)[:500]
            else:
                error = None
            await event_repository.record_publication(session, task, error)


async def run_event_worker() -> None:
    while True:
        try:
            await publish_pending_events()
        except Exception:
            logger.exception("Could not scan pending order events")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""RabbitMQ consumption for credit-service.

Subscribes to:

- ``foc.order.events`` (topic):
  - ``OrderDeletionRequested`` / ``OrderCancellationRequested`` → release the
    reservation and answer with ``CreditReleased`` / ``CreditReleaseFailed``.
  - ``OrderUpdateRequested`` → amend the reservation and answer with
    ``CreditAmended`` / ``CreditAmendRejected``.
  - ``OrderCompleted`` → transfer the credits to the courier.
  - ``OrderExpired`` → release the reservation (legacy event, no reply).
  - ``CourierWithdrawn`` → no-op, credits stay reserved (F4.1.2).
- ``foc.user.events`` (fanout): ``UserRegistered`` → initial account
  provisioning (F1.1).

Replies go to ``foc.credit.events`` with the event type as routing key.

Transient failures (broker/database) are retried by republishing the message
with an incremented ``x-retry-count`` header. After
``settings.event_retry_limit`` attempts a request event publishes its
definitive failure reply instead of looping forever; legacy lifecycle events
keep requeueing. Malformed payloads and business errors are dead-lettered or
acknowledged as before.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial

import aio_pika
from pydantic import ValidationError

from app.config import settings
from app.db import SessionLocal
from app.errors import ServiceError
from app.schemas.interop import (
    RELEASE_REQUEST_EVENT_TYPES,
    OrderActionEvent,
    OrderApprovalRequestedEvent,
    OrderUpdateRequestedEvent,
)
from app.services.credit_service import CreditService
from foc_shared.events import OrderEvent, OrderEventType, UserRegisteredEvent

logger = logging.getLogger(__name__)

_ORDER_EVENT_BINDINGS: tuple[str, ...] = (
    OrderEventType.ORDER_COMPLETED.value,
    OrderEventType.COURIER_WITHDRAWN.value,
    OrderEventType.ORDER_EXPIRED.value,
    *RELEASE_REQUEST_EVENT_TYPES,
    "OrderUpdateRequested",
    "OrderApprovalRequested",
)


async def handle_order_event(event: OrderEvent) -> None:
    """Legacy lifecycle events (completion / expiry / withdrawal)."""
    async with SessionLocal() as session:
        await CreditService(session).handle_order_event(event)


async def handle_release_requested(event: OrderActionEvent) -> None:
    async with SessionLocal() as session:
        await CreditService(session).handle_release_requested(event)


async def handle_update_requested(event: OrderUpdateRequestedEvent) -> None:
    async with SessionLocal() as session:
        await CreditService(session).handle_update_requested(event)


async def handle_approval_requested(event: OrderApprovalRequestedEvent) -> None:
    async with SessionLocal() as session:
        await CreditService(session).handle_approval_requested(event)


async def handle_user_registered_event(event: UserRegisteredEvent) -> None:
    async with SessionLocal() as session:
        await CreditService(session).handle_user_registered_event(event)


async def _release_retries_exhausted(event: OrderActionEvent, error: Exception) -> None:
    """Answer a release task we could not process within the retry budget."""
    async with SessionLocal() as session:
        await CreditService(session).report_release_retries_exhausted(event, error)


async def _amend_retries_exhausted(event: OrderUpdateRequestedEvent, error: Exception) -> None:
    """Answer an amendment task we could not process within the retry budget."""
    async with SessionLocal() as session:
        await CreditService(session).report_amend_retries_exhausted(event, error)


async def _transfer_retries_exhausted(event: OrderApprovalRequestedEvent, error: Exception) -> None:
    """Answer an approval-transfer task we could not process within the budget."""
    async with SessionLocal() as session:
        await CreditService(session).report_transfer_retries_exhausted(event, error)


class CreditEventConsumer:
    """Long-running consumer started from the app lifespan."""

    def __init__(self) -> None:
        self._stop = asyncio.Event()

    async def run(self) -> None:
        """Reconnect loop: survives broker outages and connection loss."""
        while True:
            try:
                connection = await aio_pika.connect_robust(settings.rabbitmq_url)
                async with connection:
                    await self._consume(connection)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Credit event consumer crashed; reconnecting in 5s.")
                await asyncio.sleep(5)

    async def _consume(self, connection: aio_pika.abc.AbstractRobustConnection) -> None:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        order_exchange = await channel.declare_exchange(
            settings.order_events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
        )
        order_queue = await channel.declare_queue(settings.order_events_queue, durable=True)
        for routing_key in _ORDER_EVENT_BINDINGS:
            await order_queue.bind(order_exchange, routing_key=routing_key)
        await order_queue.consume(partial(self._on_order_message, exchange=order_exchange))

        user_exchange = await channel.declare_exchange(
            settings.user_events_exchange, aio_pika.ExchangeType.FANOUT, durable=True
        )
        user_queue = await channel.declare_queue(settings.user_events_queue, durable=True)
        await user_queue.bind(user_exchange)
        await user_queue.consume(
            partial(self._dispatch, model=UserRegisteredEvent, handler=handle_user_registered_event)
        )

        logger.info(
            "Credit event consumer started (queue %s on %s; queue %s on %s).",
            settings.order_events_queue,
            settings.order_events_exchange,
            settings.user_events_queue,
            settings.user_events_exchange,
        )
        await self._stop.wait()

    async def _on_order_message(
        self,
        message: aio_pika.abc.AbstractIncomingMessage,
        *,
        exchange: aio_pika.abc.AbstractExchange,
    ) -> None:
        """Route an order event to the handler for its routing key."""
        event_type = message.routing_key
        if event_type in RELEASE_REQUEST_EVENT_TYPES:
            await self._dispatch(
                message,
                model=OrderActionEvent,
                handler=handle_release_requested,
                retry_exchange=exchange,
                on_exhausted=_release_retries_exhausted,
                verify_routing_key=True,
            )
        elif event_type == "OrderUpdateRequested":
            await self._dispatch(
                message,
                model=OrderUpdateRequestedEvent,
                handler=handle_update_requested,
                retry_exchange=exchange,
                on_exhausted=_amend_retries_exhausted,
                verify_routing_key=True,
            )
        elif event_type == "OrderApprovalRequested":
            await self._dispatch(
                message,
                model=OrderApprovalRequestedEvent,
                handler=handle_approval_requested,
                retry_exchange=exchange,
                on_exhausted=_transfer_retries_exhausted,
                verify_routing_key=True,
            )
        else:
            await self._dispatch(
                message,
                model=OrderEvent,
                handler=handle_order_event,
                verify_routing_key=True,
            )

    async def _dispatch(
        self,
        message: aio_pika.abc.AbstractIncomingMessage,
        *,
        model,
        handler,
        retry_exchange: aio_pika.abc.AbstractExchange | None = None,
        on_exhausted=None,
        verify_routing_key: bool = False,
    ) -> None:
        event = None
        try:
            event = model.model_validate_json(message.body)
            if verify_routing_key:
                event_type = getattr(event.event_type, "value", event.event_type)
                if event_type != message.routing_key:
                    # A payload/routing-key mismatch means the publisher and the
                    # consumer disagree about the contract; retrying cannot fix it.
                    logger.error(
                        "Event routing key mismatch (routing_key=%s, event_type=%s); "
                        "dead-lettering.",
                        message.routing_key,
                        event_type,
                    )
                    await message.nack(requeue=False)
                    return
            await handler(event)
        except ValidationError:
            # Malformed or out-of-date payload: dead-letter it. Requeueing
            # would retry it forever and clog the queue.
            logger.error(
                "Invalid event payload; dead-lettering (body=%s)", message.body, exc_info=True
            )
            await message.nack(requeue=False)
        except ServiceError:
            # Data/business mismatch (e.g. completion with no reservation):
            # log and acknowledge so a poison message does not loop forever.
            logger.error(
                "Business error handling event; acknowledging (body=%s)",
                message.body,
                exc_info=True,
            )
            await message.ack()
        except Exception as exc:
            if event is None:
                logger.exception("Failed to handle event; requeueing (body=%s)", message.body)
                await message.nack(requeue=True)
                return
            await self._handle_transient_failure(message, event, exc, retry_exchange, on_exhausted)
        else:
            await message.ack()

    async def _handle_transient_failure(
        self,
        message: aio_pika.abc.AbstractIncomingMessage,
        event,
        error: Exception,
        exchange: aio_pika.abc.AbstractExchange | None,
        on_exhausted,
    ) -> None:
        """Retry a transient failure, or answer definitively once out of budget."""
        if exchange is None or on_exhausted is None:
            # Legacy lifecycle events have no reply contract: keep retrying.
            logger.error(
                "Failed to handle event; requeueing (body=%s)", message.body, exc_info=error
            )
            await message.nack(requeue=True)
            return

        attempts = int((message.headers or {}).get("x-retry-count", 0))
        if attempts + 1 >= settings.event_retry_limit:
            logger.error(
                "Retry limit (%s) reached for task_id=%s; publishing a definitive failure.",
                settings.event_retry_limit,
                event.task_id,
                exc_info=error,
            )
            try:
                await on_exhausted(event, error)
            except Exception:
                logger.exception("Could not publish the failure reply; requeueing.")
                await message.nack(requeue=True)
            else:
                await message.ack()
            return

        logger.warning(
            "Transient failure (attempt %s/%s); republishing the event.",
            attempts + 1,
            settings.event_retry_limit,
            exc_info=error,
        )
        try:
            await exchange.publish(
                aio_pika.Message(
                    body=message.body,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    headers={**(message.headers or {}), "x-retry-count": attempts + 1},
                ),
                routing_key=message.routing_key,
            )
        except Exception:
            logger.exception("Could not republish the event; requeueing the original.")
            await message.nack(requeue=True)
        else:
            await message.ack()

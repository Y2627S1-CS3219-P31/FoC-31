# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

from datetime import UTC, datetime

from app.config import settings
from app.errors import NotFoundError
from app.schemas.interop import OrderActionEvent
from app.services.consumer import CreditEventConsumer
from foc_shared.events import OrderEvent, OrderEventType


class FakeMessage:
    """Minimal stand-in for aio_pika's incoming message."""

    def __init__(self, body: bytes, *, routing_key: str = "", headers: dict | None = None) -> None:
        self.body = body
        self.routing_key = routing_key
        self.headers = headers or {}
        self.acked = False
        self.rejected = False
        self.requeued: bool | None = None

    async def ack(self) -> None:
        self.acked = True

    async def nack(self, requeue: bool | None = None) -> None:
        self.rejected = True
        self.requeued = requeue


class FakeExchange:
    """Captures republished messages."""

    def __init__(self) -> None:
        self.published: list[tuple[bytes, str, dict]] = []

    async def publish(self, message, routing_key: str = "") -> None:
        self.published.append((message.body, routing_key, dict(message.headers or {})))


def _order_event() -> OrderEvent:
    return OrderEvent(
        event_type=OrderEventType.ORDER_COMPLETED,
        order_id="order-1",
        requester_id="requester",
        courier_id="courier",
        timestamp=datetime.now(UTC),
    )


def _release_event() -> OrderActionEvent:
    return OrderActionEvent(
        event_type="OrderDeletionRequested",
        task_id="task-1",
        order_id="order-1",
        reservation_id="reservation-1",
        requester_id="requester",
        timestamp=datetime.now(UTC),
    )


async def _noop(event) -> None:
    return None


async def _noop_exhausted(event, error) -> None:
    return None


async def test_invalid_payload_is_dead_lettered():
    consumer = CreditEventConsumer()
    message = FakeMessage(b"{not valid json")
    await consumer._dispatch(message, model=OrderEvent, handler=_noop)
    assert message.rejected is True
    assert message.requeued is False  # dead-lettered, never requeued


async def test_business_error_is_acknowledged():
    async def handler(event):
        raise NotFoundError("No reservation exists for order 'order-1'.")

    consumer = CreditEventConsumer()
    message = FakeMessage(_order_event().model_dump_json().encode())
    await consumer._dispatch(message, model=OrderEvent, handler=handler)
    assert message.acked is True


async def test_transient_error_is_requeued():
    async def handler(event):
        raise RuntimeError("database unavailable")

    consumer = CreditEventConsumer()
    message = FakeMessage(_order_event().model_dump_json().encode())
    await consumer._dispatch(message, model=OrderEvent, handler=handler)
    assert message.rejected is True
    assert message.requeued is True


async def test_valid_event_is_acknowledged():
    consumer = CreditEventConsumer()
    message = FakeMessage(_order_event().model_dump_json().encode())
    await consumer._dispatch(message, model=OrderEvent, handler=_noop)
    assert message.acked is True


async def test_routing_key_mismatch_is_dead_lettered():
    consumer = CreditEventConsumer()
    message = FakeMessage(_order_event().model_dump_json().encode(), routing_key="OrderExpired")
    await consumer._dispatch(message, model=OrderEvent, handler=_noop, verify_routing_key=True)
    assert message.rejected is True
    assert message.requeued is False


async def test_request_event_is_republished_before_the_limit():
    async def handler(event):
        raise RuntimeError("database unavailable")

    exchange = FakeExchange()
    consumer = CreditEventConsumer()
    message = FakeMessage(
        _release_event().model_dump_json().encode(), routing_key="OrderDeletionRequested"
    )

    await consumer._dispatch(
        message,
        model=OrderActionEvent,
        handler=handler,
        retry_exchange=exchange,
        on_exhausted=_noop_exhausted,
        verify_routing_key=True,
    )

    assert message.acked is True
    assert len(exchange.published) == 1
    body, routing_key, headers = exchange.published[0]
    assert body == message.body
    assert routing_key == "OrderDeletionRequested"
    assert headers["x-retry-count"] == 1


async def test_request_event_reports_failure_at_the_retry_limit():
    exhausted: list[tuple[str, str]] = []

    async def handler(event):
        raise RuntimeError("database unavailable")

    async def on_exhausted(event, error):
        exhausted.append((event.task_id, str(error)))

    consumer = CreditEventConsumer()
    message = FakeMessage(
        _release_event().model_dump_json().encode(),
        routing_key="OrderDeletionRequested",
        headers={"x-retry-count": settings.event_retry_limit - 1},
    )

    await consumer._dispatch(
        message,
        model=OrderActionEvent,
        handler=handler,
        retry_exchange=FakeExchange(),
        on_exhausted=on_exhausted,
        verify_routing_key=True,
    )

    assert message.acked is True
    assert exhausted == [("task-1", "database unavailable")]


async def test_legacy_event_keeps_requeueing_after_the_limit():
    async def handler(event):
        raise RuntimeError("database unavailable")

    consumer = CreditEventConsumer()
    message = FakeMessage(
        _order_event().model_dump_json().encode(),
        routing_key="OrderCompleted",
        headers={"x-retry-count": settings.event_retry_limit},
    )
    await consumer._dispatch(message, model=OrderEvent, handler=handler, verify_routing_key=True)
    assert message.requeued is True


async def test_approval_request_is_routed_to_the_transfer_handler(monkeypatch):
    from app.schemas.interop import OrderApprovalRequestedEvent
    from app.services import consumer as consumer_module

    handled: list[OrderApprovalRequestedEvent] = []

    async def handler(event):
        handled.append(event)

    monkeypatch.setattr(consumer_module, "handle_approval_requested", handler)
    event = OrderApprovalRequestedEvent(
        task_id="task-1",
        order_id="order-1",
        reservation_id="reservation-1",
        requester_id="requester",
        courier_id="courier",
        timestamp=datetime.now(UTC),
    )
    message = FakeMessage(event.model_dump_json().encode(), routing_key="OrderApprovalRequested")

    await CreditEventConsumer()._on_order_message(message, exchange=FakeExchange())

    assert message.acked is True
    assert [e.task_id for e in handled] == ["task-1"]

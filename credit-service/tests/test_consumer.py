# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

from datetime import UTC, datetime

from app.errors import NotFoundError
from app.services.consumer import CreditEventConsumer
from foc_shared.events import OrderEvent, OrderEventType


class FakeMessage:
    """Minimal stand-in for aio_pika's incoming message."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.acked = False
        self.rejected = False
        self.requeued: bool | None = None

    async def ack(self) -> None:
        self.acked = True

    async def nack(self, requeue: bool | None = None) -> None:
        self.rejected = True
        self.requeued = requeue


def _order_event() -> OrderEvent:
    return OrderEvent(
        event_type=OrderEventType.ORDER_COMPLETED,
        order_id="order-1",
        requester_id="requester",
        courier_id="courier",
        timestamp=datetime.now(UTC),
    )


async def _noop(event) -> None:
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

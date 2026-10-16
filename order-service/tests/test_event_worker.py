# AI-INFLUENCED: Durable order event retry tests implemented with Codex.
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import aio_pika
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.order_event_outbox import OrderEventOutbox
from app.repositories import order_event_outbox
from app.schemas.order_action_events import OrderCancellationFailedEvent
from app.services import event_worker, events
from foc_shared.events import OrderEvent, OrderEventType


@pytest.fixture
async def event_store():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(OrderEventOutbox.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session, session.begin():
        task = await order_event_outbox.create_event(
            session,
            OrderEvent(
                event_type=OrderEventType.ORDER_ACCEPTED,
                order_id="order-1",
                requester_id="requester-1",
                courier_id="courier-1",
                timestamp=datetime.now(UTC),
            ),
        )
    yield sessions, task.event_id
    await engine.dispose()


async def test_failed_publication_retries_same_event_then_stops(event_store, monkeypatch):
    sessions, event_id = event_store
    monkeypatch.setattr(event_worker, "SessionLocal", sessions)
    publish = AsyncMock(side_effect=[RuntimeError("broker unavailable"), None])
    monkeypatch.setattr(event_worker, "publish_order_event", publish)

    await event_worker.publish_pending_events()
    async with sessions() as session:
        task = await session.get(OrderEventOutbox, event_id)
        assert task.published_at is None
        assert task.attempts == 1
        assert task.last_error == "broker unavailable"

    await event_worker.publish_pending_events()
    await event_worker.publish_pending_events()
    async with sessions() as session:
        task = await session.get(OrderEventOutbox, event_id)
        assert task.published_at is not None
        assert task.attempts == 2
        assert task.last_error is None
    assert publish.await_count == 2
    assert publish.await_args_list[0] == publish.await_args_list[1]
    assert publish.await_args.kwargs["event_id"] == event_id


async def test_confirmation_followed_by_db_failure_retries_same_message(event_store, monkeypatch):
    sessions, event_id = event_store
    monkeypatch.setattr(event_worker, "SessionLocal", sessions)
    publish = AsyncMock()
    monkeypatch.setattr(event_worker, "publish_order_event", publish)
    original = order_event_outbox.record_publication
    monkeypatch.setattr(
        order_event_outbox, "record_publication", AsyncMock(side_effect=RuntimeError("db failed"))
    )
    with pytest.raises(RuntimeError, match="db failed"):
        await event_worker.publish_pending_events()
    async with sessions() as session:
        assert (await session.get(OrderEventOutbox, event_id)).published_at is None
    monkeypatch.setattr(order_event_outbox, "record_publication", original)
    await event_worker.publish_pending_events()
    assert publish.await_count == 2
    assert publish.await_args_list[0] == publish.await_args_list[1]


async def test_publisher_uses_shared_schema_and_confirmed_persistent_delivery(monkeypatch):
    exchange = MagicMock()
    exchange.publish = AsyncMock()
    channel = MagicMock()
    channel.declare_exchange = AsyncMock(return_value=exchange)
    connection = AsyncMock()
    connection.__aenter__.return_value = connection
    connection.channel.return_value = channel
    monkeypatch.setattr(events.aio_pika, "connect_robust", AsyncMock(return_value=connection))
    event = OrderEvent(
        event_type=OrderEventType.ORDER_ACCEPTED,
        order_id="order-1",
        requester_id="requester-1",
        courier_id="courier-1",
        timestamp=datetime.now(UTC),
    )
    await events.publish_order_event(event, event_id="event-1")
    connection.channel.assert_awaited_once_with(publisher_confirms=True, on_return_raises=True)
    message = exchange.publish.await_args.args[0]
    assert message.message_id == "event-1"
    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert OrderEvent.model_validate_json(message.body) == event
    assert exchange.publish.await_args.kwargs == {
        "routing_key": "OrderAccepted",
        "mandatory": True,
        "timeout": 5,
    }


async def test_publisher_supports_order_cancellation_failed(monkeypatch):
    exchange = MagicMock()
    exchange.publish = AsyncMock()
    channel = MagicMock()
    channel.declare_exchange = AsyncMock(return_value=exchange)
    connection = AsyncMock()
    connection.__aenter__.return_value = connection
    connection.channel.return_value = channel
    monkeypatch.setattr(events.aio_pika, "connect_robust", AsyncMock(return_value=connection))
    event = OrderCancellationFailedEvent(
        task_id="task-1",
        order_id="order-1",
        reservation_id="reservation-1",
        requester_id="requester-1",
        timestamp=datetime.now(UTC),
        reason="release_rejected",
    )

    await events.publish_order_event(event, event_id="event-1")

    message = exchange.publish.await_args.args[0]
    assert OrderCancellationFailedEvent.model_validate_json(message.body) == event
    assert exchange.publish.await_args.kwargs["routing_key"] == "OrderCancellationFailed"

# AI-INFLUENCED: Verify atomic supplier deactivation and retriable fact delivery with Codex.
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import aio_pika
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models.supplier_event_outbox import SupplierEventOutbox
from app.repositories import supplier_repo
from app.repositories.supplier_repo import SupplierRepository
from app.schemas.supplier import SupplierCreate
from app.schemas.supplier_events import SUPPLIER_EVENTS_EXCHANGE, SupplierDeactivatedEvent
from app.services import event_worker


async def test_deactivation_commits_one_supplier_fact(session) -> None:
    repo = SupplierRepository(session)
    supplier = await repo.create(SupplierCreate(name="Cool Spot", category="Food", building="Com2"))

    result = await repo.deactivate(supplier.id)
    assert result is not None and result.active is False
    assert await repo.deactivate(supplier.id) is None

    facts = (await session.scalars(select(SupplierEventOutbox))).all()
    assert len(facts) == 1
    event = SupplierDeactivatedEvent.model_validate(facts[0].payload)
    assert event.supplier_id == supplier.id
    assert event.event_id == facts[0].event_id
    assert event.event_type == "SupplierDeactivated"


async def test_deactivation_rolls_back_when_fact_cannot_be_stored(session, monkeypatch) -> None:
    repo = SupplierRepository(session)
    supplier = await repo.create(SupplierCreate(name="Cool Spot", category="Food", building="Com2"))

    def fail_outbox_write(**_kwargs):
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(supplier_repo, "SupplierEventOutbox", fail_outbox_write)
    with pytest.raises(RuntimeError, match="outbox unavailable"):
        await repo.deactivate(supplier.id)

    assert (await repo.get(supplier.id)).active is True
    assert (await session.scalars(select(SupplierEventOutbox))).all() == []


async def test_outbox_retries_same_fact_after_publish_failure(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(event_worker, "SessionLocal", sessions)

    async with sessions() as session:
        repo = SupplierRepository(session)
        supplier = await repo.create(
            SupplierCreate(name="Cool Spot", category="Food", building="Com2")
        )
        await repo.deactivate(supplier.id)

    publish = AsyncMock(side_effect=[RuntimeError("broker unavailable"), None])
    monkeypatch.setattr(event_worker, "publish_supplier_event", publish)
    try:
        await event_worker.publish_pending_events()
        async with sessions() as session:
            row = await session.scalar(select(SupplierEventOutbox))
            assert row.attempts == 1
            assert row.published_at is None
            assert row.last_error == "broker unavailable"

        await event_worker.publish_pending_events()
        async with sessions() as session:
            row = await session.scalar(select(SupplierEventOutbox))
            assert row.attempts == 2
            assert row.published_at is not None
            assert row.last_error is None

        assert publish.await_count == 2
        first_event = publish.await_args_list[0].args[0]
        second_event = publish.await_args_list[1].args[0]
        assert first_event.event_id == second_event.event_id
    finally:
        await engine.dispose()


async def test_publisher_sends_confirmed_persistent_fact(monkeypatch) -> None:
    exchange = MagicMock()
    exchange.publish = AsyncMock()
    channel = MagicMock()
    channel.declare_exchange = AsyncMock(return_value=exchange)
    connection = AsyncMock()
    connection.__aenter__.return_value = connection
    connection.channel.return_value = channel
    monkeypatch.setattr(event_worker.aio_pika, "connect_robust", AsyncMock(return_value=connection))
    fact = SupplierDeactivatedEvent(
        event_id="fact-1", supplier_id="supplier-1", timestamp=datetime.now(UTC)
    )

    await event_worker.publish_supplier_event(fact)

    connection.channel.assert_awaited_once_with(publisher_confirms=True, on_return_raises=True)
    channel.declare_exchange.assert_awaited_once_with(
        SUPPLIER_EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
    )
    message = exchange.publish.await_args.args[0]
    assert message.message_id == fact.event_id
    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert SupplierDeactivatedEvent.model_validate_json(message.body) == fact
    assert exchange.publish.await_args.kwargs == {
        "routing_key": "SupplierDeactivated",
        "mandatory": True,
        "timeout": 5,
    }

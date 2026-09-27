# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

from datetime import UTC, datetime

from app.models.reservation import ReservationStatus
from app.services import publisher
from app.services.credit_service import CreditService
from foc_shared.events import OrderEvent, OrderEventType, UserRegisteredEvent


async def _noop_publish(event) -> None:
    return None


def _order_event(
    event_type: OrderEventType,
    *,
    order_id: str = "order-1",
    requester_id: str = "requester",
    courier_id: str | None = "courier",
) -> OrderEvent:
    return OrderEvent(
        event_type=event_type,
        order_id=order_id,
        requester_id=requester_id,
        courier_id=courier_id,
        timestamp=datetime.now(UTC),
    )


async def _setup(service: CreditService) -> None:
    await service.ensure_account("requester")
    await service.ensure_account("courier")
    await service.reserve(user_id="requester", order_id="order-1", amount=40)


async def test_order_completed_transfers_credits(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    await _setup(service)

    await service.handle_order_event(_order_event(OrderEventType.ORDER_COMPLETED))

    requester = await service.get_balances("requester")
    assert requester.reserved_balance == 0
    courier = await service.get_balances("courier")
    assert courier.available_balance == 140


async def test_order_completed_is_idempotent(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    await _setup(service)

    event = _order_event(OrderEventType.ORDER_COMPLETED)
    await service.handle_order_event(event)
    await service.handle_order_event(event)  # redelivery

    courier = await service.get_balances("courier")
    assert courier.available_balance == 140


async def test_order_completed_without_courier_keeps_reserved(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    await _setup(service)

    event = _order_event(OrderEventType.ORDER_COMPLETED, courier_id=None)
    await service.handle_order_event(event)

    requester = await service.get_balances("requester")
    assert requester.available_balance == 60
    assert requester.reserved_balance == 40


async def test_order_cancelled_releases_credits(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    await _setup(service)

    await service.handle_order_event(_order_event(OrderEventType.ORDER_CANCELLED))

    requester = await service.get_balances("requester")
    assert requester.available_balance == 100
    assert requester.reserved_balance == 0
    reservation = await service._reservations.get_by_order_id("order-1")
    assert reservation.status == ReservationStatus.RELEASED.value


async def test_order_expired_releases_credits(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    await _setup(service)

    await service.handle_order_event(_order_event(OrderEventType.ORDER_EXPIRED))

    requester = await service.get_balances("requester")
    assert requester.available_balance == 100
    assert requester.reserved_balance == 0


async def test_courier_withdrawn_keeps_credits_reserved(session, monkeypatch):
    """Credit F4.1.2: withdrawal must NOT release the reservation."""
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    await _setup(service)

    await service.handle_order_event(_order_event(OrderEventType.COURIER_WITHDRAWN))

    requester = await service.get_balances("requester")
    assert requester.available_balance == 60  # unchanged
    assert requester.reserved_balance == 40
    reservation = await service._reservations.get_by_order_id("order-1")
    assert reservation.status == ReservationStatus.RESERVED.value


async def test_user_registered_provisions_account(session):
    service = CreditService(session)
    await service.handle_user_registered_event(
        UserRegisteredEvent(user_id="new-user", email="new@u.nus.edu")
    )
    account = await service.get_balances("new-user")
    assert account.available_balance == 100
    assert account.reserved_balance == 0


async def test_user_registered_is_idempotent(session):
    service = CreditService(session)
    event = UserRegisteredEvent(user_id="new-user", email="new@u.nus.edu")
    await service.handle_user_registered_event(event)
    await service.handle_user_registered_event(event)  # redelivery
    account = await service.get_balances("new-user")
    assert account.available_balance == 100

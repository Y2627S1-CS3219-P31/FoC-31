# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

import pytest

from app.errors import ConflictError, InsufficientCreditsError, NotFoundError
from app.models.reservation import ReservationStatus
from app.models.transaction import TransactionKind
from app.services import publisher
from app.services.credit_service import CreditService
from foc_shared.events import CreditEventType


def _collect(events: list) -> object:
    async def fake_publish(event) -> None:
        events.append(event)

    return fake_publish


async def _reserve(
    service: CreditService,
    *,
    user_id: str = "user-1",
    order_id: str = "order-1",
    amount: int = 40,
):
    await service.ensure_account(user_id)
    return await service.reserve(user_id=user_id, order_id=order_id, amount=amount)


async def test_reserve_moves_available_to_reserved(session, monkeypatch):
    events: list = []
    monkeypatch.setattr(publisher, "publish_reservation_event", _collect(events))
    service = CreditService(session)

    reservation = await _reserve(service)

    account = await service.get_balances("user-1")
    assert account.available_balance == 60
    assert account.reserved_balance == 40
    assert reservation.status == ReservationStatus.RESERVED.value

    transactions = await service.list_transactions("user-1")
    reservation_txn = next(t for t in transactions if t.kind == TransactionKind.RESERVATION.value)
    assert reservation_txn.amount == -40
    assert reservation_txn.order_id == "order-1"
    assert reservation_txn.reservation_id == reservation.id

    assert [e.event_type for e in events] == [CreditEventType.CREDIT_RESERVATION_ACCEPTED]
    assert events[0].reservation_id == reservation.id
    assert events[0].user_id == "user-1"
    assert events[0].order_id == "order-1"
    assert events[0].amount == 40


async def test_reserve_rejects_insufficient_credits(session, monkeypatch):
    events: list = []
    monkeypatch.setattr(publisher, "publish_reservation_event", _collect(events))
    service = CreditService(session)
    await service.ensure_account("user-1")

    with pytest.raises(InsufficientCreditsError):
        await service.reserve(user_id="user-1", order_id="order-1", amount=150)

    account = await service.get_balances("user-1")
    assert account.available_balance == 100  # untouched
    assert account.reserved_balance == 0
    assert [e.event_type for e in events] == [CreditEventType.CREDIT_RESERVATION_REJECTED]
    assert events[0].reason == "insufficient available credits"
    # Only the initial allocation is recorded; no reservation transaction.
    assert len(await service.list_transactions("user-1")) == 1


async def test_reserve_requires_an_account(session):
    service = CreditService(session)
    with pytest.raises(NotFoundError):
        await service.reserve(user_id="ghost", order_id="order-1", amount=10)


async def test_reserve_retry_same_amount_returns_existing(session, monkeypatch):
    """Order-service retrying after a timeout gets the existing reservation
    back instead of a 409 (idempotent retry)."""
    events: list = []
    monkeypatch.setattr(publisher, "publish_reservation_event", _collect(events))
    service = CreditService(session)
    first = await _reserve(service)

    second = await service.reserve(user_id="user-1", order_id="order-1", amount=40)

    assert second.id == first.id
    account = await service.get_balances("user-1")
    assert account.available_balance == 60  # no double deduction
    accepted = [e for e in events if e.event_type == CreditEventType.CREDIT_RESERVATION_ACCEPTED]
    assert len(accepted) == 1  # no duplicate event


async def test_reserve_same_order_different_amount_conflicts(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _collect([]))
    service = CreditService(session)
    await _reserve(service)
    with pytest.raises(ConflictError):
        await service.reserve(user_id="user-1", order_id="order-1", amount=10)
    account = await service.get_balances("user-1")
    assert account.available_balance == 60  # only one reservation happened


async def test_reserve_never_drives_balance_negative(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _collect([]))
    service = CreditService(session)
    await _reserve(service, amount=100)
    account = await service.get_balances("user-1")
    assert account.available_balance == 0
    assert account.reserved_balance == 100
    with pytest.raises(InsufficientCreditsError):
        await service.reserve(user_id="user-1", order_id="order-2", amount=1)


async def test_reserve_concurrent_duplicate_yields_conflict(session, monkeypatch):
    """Simulates the pre-check racing with another worker: get_by_order_id
    sees nothing, but the row already exists, so the unique order_id
    constraint fires at flush and must surface as a clean 409."""
    monkeypatch.setattr(publisher, "publish_reservation_event", _collect([]))
    service = CreditService(session)
    await _reserve(service)  # a reservation for order-1 now exists

    async def _race(order_id):
        return None  # pretend the check ran before the other worker inserted

    monkeypatch.setattr(service._reservations, "get_by_order_id", _race)
    with pytest.raises(ConflictError):
        await service.reserve(user_id="user-1", order_id="order-1", amount=10)

    account = await service.get_balances("user-1")
    assert account.available_balance == 60  # losing insert fully rolled back
    assert account.reserved_balance == 40


async def test_reserve_concurrent_identical_retry_returns_existing(session, monkeypatch):
    """A concurrent duplicate with identical parameters is treated as a
    successful retry, not a conflict."""
    monkeypatch.setattr(publisher, "publish_reservation_event", _collect([]))
    service = CreditService(session)
    await _reserve(service)

    original = service._reservations.get_by_order_id
    state = {"calls": 0}

    async def _race(order_id):
        if state["calls"] == 0:
            state["calls"] += 1
            return None  # only the pre-check races; the re-query sees the row
        return await original(order_id)

    monkeypatch.setattr(service._reservations, "get_by_order_id", _race)
    second = await service.reserve(user_id="user-1", order_id="order-1", amount=40)

    assert second.amount == 40
    account = await service.get_balances("user-1")
    assert account.available_balance == 60

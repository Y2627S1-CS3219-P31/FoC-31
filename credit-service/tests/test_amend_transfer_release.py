# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

import pytest

from app.errors import ConflictError, ForbiddenError, InsufficientCreditsError, NotFoundError
from app.models.reservation import ReservationStatus
from app.models.transaction import TransactionKind
from app.services import publisher
from app.services.credit_service import CreditService
from foc_shared.auth import Role


async def _noop_publish(event) -> None:
    return None


async def _setup(service: CreditService, *, reserve: int = 40):
    await service.ensure_account("requester")
    await service.ensure_account("courier")
    reservation = await service.reserve(user_id="requester", order_id="order-1", amount=reserve)
    return reservation


# ── F2.3 amendment ─────────────────────────────────────────────────────────


async def test_amend_increase_revalidates_available(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    reservation = await _setup(service)

    amended = await service.amend(
        reservation.id, 90, caller_user_id="requester", caller_role=Role.CLIENT.value
    )
    assert amended.amount == 90
    account = await service.get_balances("requester")
    assert account.available_balance == 10
    assert account.reserved_balance == 90


async def test_amend_increase_rejects_when_insufficient(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    reservation = await _setup(service)

    with pytest.raises(InsufficientCreditsError):
        await service.amend(
            reservation.id,
            500,
            caller_user_id="requester",
            caller_role=Role.CLIENT.value,
        )
    account = await service.get_balances("requester")
    assert account.available_balance == 60  # unchanged
    assert account.reserved_balance == 40


async def test_amend_decrease_returns_difference(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    reservation = await _setup(service)

    amended = await service.amend(
        reservation.id, 10, caller_user_id="requester", caller_role=Role.CLIENT.value
    )
    assert amended.amount == 10
    account = await service.get_balances("requester")
    assert account.available_balance == 90
    assert account.reserved_balance == 10


async def test_amend_by_other_user_forbidden(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    reservation = await _setup(service)

    with pytest.raises(ForbiddenError):
        await service.amend(
            reservation.id, 50, caller_user_id="courier", caller_role=Role.CLIENT.value
        )


# ── F3 transfer ────────────────────────────────────────────────────────────


async def test_transfer_moves_reserved_credits_to_courier(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    await _setup(service)

    transferred = await service.transfer_for_order("order-1", "courier")
    assert transferred.status == ReservationStatus.TRANSFERRED.value

    requester = await service.get_balances("requester")
    assert requester.available_balance == 60
    assert requester.reserved_balance == 0
    courier = await service.get_balances("courier")
    assert courier.available_balance == 140

    courier_txns = await service.list_transactions("courier")
    transfer_txn = next(t for t in courier_txns if t.kind == TransactionKind.TRANSFER.value)
    assert transfer_txn.amount == 40
    assert transfer_txn.counterparty_user_id == "requester"
    assert transfer_txn.order_id == "order-1"

    requester_txns = await service.list_transactions("requester")
    requester_transfer = next(t for t in requester_txns if t.kind == TransactionKind.TRANSFER.value)
    assert requester_transfer.amount == 0  # outflow already recorded at reservation
    assert requester_transfer.counterparty_user_id == "courier"


async def test_transfer_is_idempotent(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    await _setup(service)

    await service.transfer_for_order("order-1", "courier")
    await service.transfer_for_order("order-1", "courier")  # repeated completion

    requester = await service.get_balances("requester")
    assert requester.available_balance == 60
    courier = await service.get_balances("courier")
    assert courier.available_balance == 140  # not 180

    courier_txns = [
        t
        for t in await service.list_transactions("courier")
        if t.kind == TransactionKind.TRANSFER.value
    ]
    assert len(courier_txns) == 1


async def test_transfer_unknown_order_raises(session):
    service = CreditService(session)
    with pytest.raises(NotFoundError):
        await service.transfer_for_order("no-such-order", "courier")


async def test_transfer_to_unknown_courier_raises(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    await service.ensure_account("requester")
    await service.reserve(user_id="requester", order_id="order-1", amount=40)

    with pytest.raises(NotFoundError):
        await service.transfer_for_order("order-1", "ghost")
    requester = await service.get_balances("requester")
    assert requester.reserved_balance == 40  # unchanged


# ── F4 release ─────────────────────────────────────────────────────────────


async def test_release_returns_reserved_credits(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    await _setup(service)

    released = await service.release_for_order("order-1")
    assert released is not None
    assert released.status == ReservationStatus.RELEASED.value

    account = await service.get_balances("requester")
    assert account.available_balance == 100
    assert account.reserved_balance == 0

    release_txn = next(
        t
        for t in await service.list_transactions("requester")
        if t.kind == TransactionKind.RELEASE.value
    )
    assert release_txn.amount == 40


async def test_release_is_idempotent(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    await _setup(service)

    await service.release_for_order("order-1")
    await service.release_for_order("order-1")  # redelivered event

    account = await service.get_balances("requester")
    assert account.available_balance == 100  # not 140
    release_txns = [
        t
        for t in await service.list_transactions("requester")
        if t.kind == TransactionKind.RELEASE.value
    ]
    assert len(release_txns) == 1


async def test_release_unknown_order_is_noop(session):
    service = CreditService(session)
    result = await service.release_for_order("no-such-order")
    assert result is None


async def test_release_after_transfer_conflicts(session, monkeypatch):
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    await _setup(service)
    await service.transfer_for_order("order-1", "courier")

    with pytest.raises(ConflictError):
        await service.release_for_order("order-1")


async def test_history_sums_to_balance_after_transfer(session, monkeypatch):
    """F5.2: income + outflow must add up to the current balance."""
    monkeypatch.setattr(publisher, "publish_reservation_event", _noop_publish)
    service = CreditService(session)
    await service.ensure_account("requester")
    await service.ensure_account("courier")
    await service.reserve(user_id="requester", order_id="order-1", amount=30)
    await service.transfer_for_order("order-1", "courier")

    requester = await service.get_balances("requester")
    requester_total = sum(t.amount for t in await service.list_transactions("requester", limit=200))
    assert requester_total == requester.available_balance + requester.reserved_balance

    courier = await service.get_balances("courier")
    courier_total = sum(t.amount for t in await service.list_transactions("courier", limit=200))
    assert courier_total == courier.available_balance + courier.reserved_balance

# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.clients import credits as credit_client_module
from app.clients.suppliers import SupplierRecord
from app.models.orders import Order
from app.services import orders as order_service


def make_order(
    *,
    requester_id: str = "user-1",
    courier_id: str | None = None,
    status: str = "OPEN",
) -> Order:
    return Order(
        id=1,
        name="Collect lunch",
        details="One vegetarian rice bowl",
        reward=5,
        deadline=datetime.now(UTC) + timedelta(hours=2),
        supplier_id="sup_001",
        pickup_location="The Deck",
        delivery_location="COM3",
        requester_id=requester_id,
        courier_id=courier_id,
        status=status,
    )


async def test_get_order_only_allows_requester(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order",
        AsyncMock(return_value=make_order(requester_id="user-1")),
    )

    with pytest.raises(order_service.OrderAccessDeniedError):
        await order_service.get_order_for_requester(object(), 1, "user-2")


async def test_create_commits_only_after_supplier_and_credit_succeed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = make_order()
    stage = AsyncMock(return_value=order)
    commit = AsyncMock()
    monkeypatch.setattr(order_service.order_repository, "stage_order", stage)
    monkeypatch.setattr(order_service.order_repository, "commit_order", commit)
    supplier_client = AsyncMock()
    supplier_client.get_supplier.return_value = SupplierRecord(id="sup_001", active=True)
    credit_client = AsyncMock()
    session = AsyncMock()

    created = await order_service.create_order(
        session,
        order_service.OrderCreate(
            name=order.name,
            details=order.details,
            reward=order.reward,
            deadline=order.deadline,
            supplier_id=order.supplier_id,
            pickup_location=order.pickup_location,
            delivery_location=order.delivery_location,
        ),
        order.requester_id,
        supplier_client,
        credit_client,
    )

    assert created is order
    supplier_client.get_supplier.assert_awaited_once_with("sup_001")
    credit_client.reserve.assert_awaited_once_with(
        order_id=1,
        requester_id="user-1",
        amount=5,
    )
    commit.assert_awaited_once_with(session)
    session.rollback.assert_not_awaited()


async def test_create_rejects_inactive_supplier_before_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = make_order()
    stage = AsyncMock()
    monkeypatch.setattr(order_service.order_repository, "stage_order", stage)
    supplier_client = AsyncMock()
    supplier_client.get_supplier.return_value = SupplierRecord(id="sup_001", active=False)
    credit_client = AsyncMock()

    with pytest.raises(order_service.SupplierInactiveError):
        await order_service.create_order(
            AsyncMock(),
            order_service.OrderCreate(
                name=order.name,
                details=order.details,
                reward=order.reward,
                deadline=order.deadline,
                supplier_id=order.supplier_id,
                pickup_location=order.pickup_location,
                delivery_location=order.delivery_location,
            ),
            order.requester_id,
            supplier_client,
            credit_client,
        )

    stage.assert_not_awaited()
    credit_client.reserve.assert_not_awaited()


async def test_create_rolls_back_when_credit_reservation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = make_order()
    monkeypatch.setattr(
        order_service.order_repository,
        "stage_order",
        AsyncMock(return_value=order),
    )
    commit = AsyncMock()
    monkeypatch.setattr(order_service.order_repository, "commit_order", commit)
    supplier_client = AsyncMock()
    supplier_client.get_supplier.return_value = SupplierRecord(id="sup_001", active=True)
    credit_client = AsyncMock()
    credit_client.reserve.side_effect = credit_client_module.CreditReservationRejectedError(
        "Insufficient credits."
    )
    session = AsyncMock()

    with pytest.raises(order_service.CreditReservationError):
        await order_service.create_order(
            session,
            order_service.OrderCreate(
                name=order.name,
                details=order.details,
                reward=order.reward,
                deadline=order.deadline,
                supplier_id=order.supplier_id,
                pickup_location=order.pickup_location,
                delivery_location=order.delivery_location,
            ),
            order.requester_id,
            supplier_client,
            credit_client,
        )

    session.rollback.assert_awaited_once()
    commit.assert_not_awaited()


async def test_delete_open_unassigned_order(monkeypatch: pytest.MonkeyPatch) -> None:
    order = make_order()
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order",
        AsyncMock(return_value=order),
    )
    delete = AsyncMock()
    monkeypatch.setattr(order_service.order_repository, "delete_order", delete)
    session = object()

    await order_service.delete_order_for_requester(session, 1, "user-1")

    delete.assert_awaited_once_with(session, order)


@pytest.mark.parametrize(
    ("courier_id", "order_status"),
    [
        ("courier-1", "OPEN"),
        (None, "ACCEPTED"),
        (None, "COMPLETED"),
    ],
)
async def test_delete_rejects_assigned_or_non_open_order(
    courier_id: str | None,
    order_status: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order",
        AsyncMock(return_value=make_order(courier_id=courier_id, status=order_status)),
    )
    delete = AsyncMock()
    monkeypatch.setattr(order_service.order_repository, "delete_order", delete)

    with pytest.raises(order_service.OrderStateConflictError):
        await order_service.delete_order_for_requester(object(), 1, "user-1")

    delete.assert_not_awaited()

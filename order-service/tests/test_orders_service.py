# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

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
    [("courier-1", "OPEN"), (None, "COMPLETED")],
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

# AI-INFLUENCED: Sprint 1 Order Service workflow tests generated with Codex.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services import orders as order_service
from app.services.errors import (
    OrderAccessDeniedError,
    OrderDeletionError,
    OrderNotFoundError,
    OrderPersistenceError,
    OrderRetrievalError,
    OrderStateConflictError,
)
from app.services.lifecycle import OrderStatus


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


class _Session:
    def begin(self) -> _Transaction:
        return _Transaction()


def _order(
    *,
    requester_id: str = "user-1",
    courier_id: str | None = None,
    status: OrderStatus = OrderStatus.OPEN,
) -> SimpleNamespace:
    return SimpleNamespace(
        order_id="order-1",
        requester_id=requester_id,
        courier_id=courier_id,
        reservation_id="reservation-1",
        status=status,
        deadline=datetime.now(UTC) + timedelta(hours=2),
    )


async def test_list_available_orders_translates_database_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        order_service.order_repository,
        "list_available_orders",
        AsyncMock(side_effect=SQLAlchemyError("database unavailable")),
    )

    with pytest.raises(OrderRetrievalError):
        await order_service.list_available_orders(_Session(), "user-1")


async def test_get_order_enforces_requester_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order",
        AsyncMock(return_value=_order(requester_id="user-1")),
    )

    with pytest.raises(OrderAccessDeniedError):
        await order_service.get_order_for_requester(
            _Session(),
            "order-1",
            "user-2",
        )


async def test_get_order_reports_missing_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order",
        AsyncMock(return_value=None),
    )

    with pytest.raises(OrderNotFoundError):
        await order_service.get_order_for_requester(
            _Session(),
            "missing",
            "user-1",
        )


async def test_delete_open_order_releases_credits_before_deleting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = _order()
    get_order = AsyncMock(return_value=order)
    release = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr(order_service.order_repository, "get_order_for_update", get_order)
    monkeypatch.setattr(order_service, "release_credits", release)
    monkeypatch.setattr(order_service.order_repository, "delete_order", delete)

    await order_service.delete_order_for_requester(
        _Session(),
        "order-1",
        "user-1",
    )

    release.assert_awaited_once_with(
        reservation_id="reservation-1",
        requester_id="user-1",
    )
    delete.assert_awaited_once_with(ANY, order)


@pytest.mark.parametrize(
    "order",
    [
        _order(courier_id="courier-1"),
        _order(status=OrderStatus.COMPLETED),
    ],
)
async def test_delete_rejects_assigned_or_non_open_order(
    monkeypatch: pytest.MonkeyPatch,
    order: SimpleNamespace,
) -> None:
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order_for_update",
        AsyncMock(return_value=order),
    )
    release = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr(order_service, "release_credits", release)
    monkeypatch.setattr(order_service.order_repository, "delete_order", delete)

    with pytest.raises(OrderStateConflictError):
        await order_service.delete_order_for_requester(
            _Session(),
            "order-1",
            "user-1",
        )

    release.assert_not_awaited()
    delete.assert_not_awaited()


async def test_delete_translates_database_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order_for_update",
        AsyncMock(side_effect=SQLAlchemyError("database unavailable")),
    )

    with pytest.raises(OrderDeletionError):
        await order_service.delete_order_for_requester(
            _Session(),
            "order-1",
            "user-1",
        )


async def test_create_releases_reservation_when_database_insert_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    new_order = SimpleNamespace(supplier_id="sup-1", reward=5)
    monkeypatch.setattr(
        order_service,
        "get_supplier",
        AsyncMock(return_value=SimpleNamespace(active=True)),
    )
    monkeypatch.setattr(
        order_service,
        "reserve_credits",
        AsyncMock(return_value=SimpleNamespace(id="reservation-1")),
    )
    monkeypatch.setattr(
        order_service.order_repository,
        "create_order",
        AsyncMock(side_effect=SQLAlchemyError("insert failed")),
    )
    release = AsyncMock()
    monkeypatch.setattr(order_service, "release_credits", release)

    with pytest.raises(OrderPersistenceError):
        await order_service.create_order(new_order, "user-1", _Session())

    release.assert_awaited_once_with(
        reservation_id="reservation-1",
        requester_id="user-1",
    )

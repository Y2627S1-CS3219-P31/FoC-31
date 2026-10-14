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
    OrderNotEditableError,
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


def _mock_credit_client(monkeypatch: pytest.MonkeyPatch, **methods: AsyncMock) -> None:
    client = SimpleNamespace(**methods)
    monkeypatch.setattr(order_service, "get_credit_client", lambda: client)


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


@pytest.mark.parametrize(
    ("status", "courier_id"),
    [
        (OrderStatus.ACCEPTED, None),
        (OrderStatus.OPEN, "courier-1"),
    ],
)
async def test_update_rejects_non_editable_order(
    monkeypatch: pytest.MonkeyPatch,
    status: OrderStatus,
    courier_id: str | None,
) -> None:
    order = _order(status=status, courier_id=courier_id)
    order.reward = 5
    update = AsyncMock()
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order",
        AsyncMock(return_value=order),
    )
    monkeypatch.setattr(order_service.order_repository, "update_order", update)

    with pytest.raises(OrderNotEditableError):
        await order_service.update_order(
            "order-1",
            SimpleNamespace(reward=5),
            "user-1",
            _Session(),
        )

    update.assert_not_awaited()


async def test_delete_open_order_releases_credits_after_committing_deletion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class RecordingTransaction:
        async def __aenter__(self):
            events.append("transaction_started")
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            events.append("deletion_committed")
            return False

    class RecordingSession:
        def begin(self) -> RecordingTransaction:
            return RecordingTransaction()

    order = _order()
    get_order = AsyncMock(return_value=order)
    release = AsyncMock(side_effect=lambda **_kwargs: events.append("credits_released"))
    delete = AsyncMock(side_effect=lambda *_args: events.append("order_deleted"))
    monkeypatch.setattr(order_service.order_repository, "get_order_for_update", get_order)
    _mock_credit_client(monkeypatch, release_credits=release)
    monkeypatch.setattr(order_service.order_repository, "delete_order", delete)

    await order_service.delete_order_for_requester(
        RecordingSession(),
        "order-1",
        "user-1",
    )

    release.assert_awaited_once_with(
        reservation_id="reservation-1",
        requester_id="user-1",
    )
    delete.assert_awaited_once_with(ANY, order)
    assert events == [
        "transaction_started",
        "order_deleted",
        "deletion_committed",
        "credits_released",
    ]


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
    _mock_credit_client(monkeypatch, release_credits=release)
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
    release = AsyncMock()
    _mock_credit_client(monkeypatch, release_credits=release)

    with pytest.raises(OrderDeletionError):
        await order_service.delete_order_for_requester(
            _Session(),
            "order-1",
            "user-1",
        )

    release.assert_not_awaited()


async def test_delete_does_not_release_credits_when_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CommitFailingTransaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, _exc, _traceback):
            if exc_type is None:
                raise SQLAlchemyError("commit failed")
            return False

    class CommitFailingSession:
        def begin(self) -> CommitFailingTransaction:
            return CommitFailingTransaction()

    order = _order()
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order_for_update",
        AsyncMock(return_value=order),
    )
    monkeypatch.setattr(order_service.order_repository, "delete_order", AsyncMock())
    release = AsyncMock()
    _mock_credit_client(monkeypatch, release_credits=release)

    with pytest.raises(OrderDeletionError):
        await order_service.delete_order_for_requester(
            CommitFailingSession(),
            "order-1",
            "user-1",
        )

    release.assert_not_awaited()


async def test_create_releases_reservation_when_database_insert_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    new_order = SimpleNamespace(supplier_id="sup-1", reward=5)
    monkeypatch.setattr(
        order_service,
        "get_supplier",
        AsyncMock(return_value=SimpleNamespace(active=True)),
    )
    reserve = AsyncMock(return_value=SimpleNamespace(id="reservation-1"))
    monkeypatch.setattr(
        order_service.order_repository,
        "create_order",
        AsyncMock(side_effect=SQLAlchemyError("insert failed")),
    )
    release = AsyncMock()
    _mock_credit_client(monkeypatch, reserve_credits=reserve, release_credits=release)

    with pytest.raises(OrderPersistenceError):
        await order_service.create_order(new_order, "user-1", _Session())

    release.assert_awaited_once_with(
        reservation_id="reservation-1",
        requester_id="user-1",
    )
    reserve.assert_awaited_once_with(5, "user-1", ANY)

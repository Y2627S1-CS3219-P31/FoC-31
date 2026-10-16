# AI-INFLUENCED: Sprint 1 Order Service workflow tests generated with Codex.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.models.order_release_outbox import ReleaseAction
from app.models.order_update_outbox import PENDING
from app.schemas.orders import OrderUpdate
from app.services import orders as order_service
from app.services.errors import (
    OrderAccessDeniedError,
    OrderCancellationError,
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


@pytest.fixture(autouse=True)
def no_release_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        order_service.release_outbox_repository,
        "get_for_order",
        AsyncMock(return_value=None),
    )


def _updated_order(reward: int = 20) -> OrderUpdate:
    return OrderUpdate(
        name="Updated order",
        details="Updated details",
        reward=reward,
        deadline=datetime.now(UTC) + timedelta(hours=2),
        supplier_id="supplier-1",
        pickup_location="Library",
        delivery_location="Dorm",
    )


def _pending_task(update: OrderUpdate) -> SimpleNamespace:
    return SimpleNamespace(
        task_id="task-1",
        order_id="order-1",
        reservation_id="reservation-1",
        requester_id="user-1",
        proposed_order=update.model_dump(mode="json"),
        status=PENDING,
        attempts=0,
        last_error=None,
        rejection_code=None,
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












async def test_delete_saves_task_without_calling_credit_or_deleting_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class RecordingTransaction:
        async def __aenter__(self):
            events.append("begin")

        async def __aexit__(self, _exc_type, _exc, _traceback):
            events.append("commit")
            return False

    class RecordingSession:
        def begin(self):
            return RecordingTransaction()

    order = _order()
    task = SimpleNamespace(task_id="task-1", order_id="order-1", status="pending")
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order_for_update",
        AsyncMock(return_value=order),
    )
    monkeypatch.setattr(
        order_service.update_outbox_repository,
        "get_pending_for_order",
        AsyncMock(return_value=None),
    )

    async def create_task(_session, **values):
        assert values["order_id"] == "order-1"
        assert values["requester_id"] == "user-1"
        assert values["reservation_id"] == "reservation-1"
        assert values["action"].value == "delete"
        events.append("task_saved")
        return task

    monkeypatch.setattr(order_service.release_outbox_repository, "create_task", create_task)
    delete = AsyncMock()
    release = AsyncMock()
    monkeypatch.setattr(order_service.order_repository, "delete_order", delete)
    _mock_credit_client(monkeypatch, release_credits=release)

    result = await order_service.delete_order_for_requester(RecordingSession(), "order-1", "user-1")

    assert result is task
    assert events == ["begin", "task_saved", "commit"]
    delete.assert_not_awaited()
    release.assert_not_awaited()


async def test_repeated_delete_returns_existing_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = SimpleNamespace(task_id="task-1", order_id="order-1", status="pending")
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order_for_update",
        AsyncMock(return_value=_order()),
    )
    monkeypatch.setattr(
        order_service.release_outbox_repository,
        "get_for_order",
        AsyncMock(return_value=task),
    )
    create = AsyncMock()
    monkeypatch.setattr(order_service.release_outbox_repository, "create_task", create)

    result = await order_service.delete_order_for_requester(_Session(), "order-1", "user-1")

    assert result is task
    create.assert_not_awaited()


async def test_cancel_creates_pending_action_for_open_or_accepted_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = _order(status=OrderStatus.ACCEPTED, courier_id="courier-1")
    task = SimpleNamespace(task_id="task-1", order_id="order-1", status="pending")
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order_for_update",
        AsyncMock(return_value=order),
    )
    monkeypatch.setattr(
        order_service.update_outbox_repository,
        "get_pending_for_order",
        AsyncMock(return_value=None),
    )
    create = AsyncMock(return_value=task)
    monkeypatch.setattr(order_service.release_outbox_repository, "create_task", create)

    result = await order_service.cancel_order_for_requester(
        _Session(), "order-1", "user-1", "Requester changed their mind"
    )

    assert result is task
    assert create.await_args.kwargs == {
        "order_id": "order-1",
        "requester_id": "user-1",
        "reservation_id": "reservation-1",
        "action": ReleaseAction.CANCEL,
        "reason": "Requester changed their mind",
    }


async def test_repeated_cancel_returns_the_same_pending_cancel_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = SimpleNamespace(action="cancel", status="pending")
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order_for_update",
        AsyncMock(return_value=_order()),
    )
    monkeypatch.setattr(
        order_service.release_outbox_repository,
        "get_for_order",
        AsyncMock(return_value=existing),
    )
    create = AsyncMock()
    monkeypatch.setattr(order_service.release_outbox_repository, "create_task", create)

    result = await order_service.cancel_order_for_requester(
        _Session(), "order-1", "user-1", "No longer needed"
    )

    assert result is existing
    create.assert_not_awaited()


@pytest.mark.parametrize(
    "existing",
    [
        SimpleNamespace(action="delete", status="pending"),
        SimpleNamespace(action="cancel", status="failed"),
    ],
)
async def test_cancel_rejects_conflicting_or_failed_terminal_action(
    monkeypatch: pytest.MonkeyPatch, existing: SimpleNamespace
) -> None:
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order_for_update",
        AsyncMock(return_value=_order()),
    )
    monkeypatch.setattr(
        order_service.release_outbox_repository,
        "get_for_order",
        AsyncMock(return_value=existing),
    )

    with pytest.raises(OrderStateConflictError):
        await order_service.cancel_order_for_requester(
            _Session(), "order-1", "user-1", "No longer needed"
        )


async def test_cancel_enforces_requester_ownership(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order_for_update",
        AsyncMock(return_value=_order(requester_id="user-1")),
    )
    create = AsyncMock()
    monkeypatch.setattr(order_service.release_outbox_repository, "create_task", create)

    with pytest.raises(OrderAccessDeniedError):
        await order_service.cancel_order_for_requester(
            _Session(), "order-1", "user-2", "No longer needed"
        )

    create.assert_not_awaited()


async def test_cancel_rejects_order_after_pickup_or_with_pending_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_order = AsyncMock(return_value=_order(status=OrderStatus.PICKED_UP))
    monkeypatch.setattr(order_service.order_repository, "get_order_for_update", get_order)

    with pytest.raises(OrderStateConflictError, match="open or accepted"):
        await order_service.cancel_order_for_requester(
            _Session(), "order-1", "user-1", "No longer needed"
        )

    get_order.return_value = _order()
    monkeypatch.setattr(
        order_service.update_outbox_repository,
        "get_pending_for_order",
        AsyncMock(return_value=_pending_task(_updated_order())),
    )
    with pytest.raises(OrderStateConflictError, match="update in progress"):
        await order_service.cancel_order_for_requester(
            _Session(), "order-1", "user-1", "No longer needed"
        )


async def test_cancel_translates_database_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order_for_update",
        AsyncMock(side_effect=SQLAlchemyError("database unavailable")),
    )

    with pytest.raises(OrderCancellationError):
        await order_service.cancel_order_for_requester(
            _Session(), "order-1", "user-1", "No longer needed"
        )


async def test_delete_rejects_order_with_pending_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order_for_update",
        AsyncMock(return_value=_order()),
    )
    monkeypatch.setattr(
        order_service.update_outbox_repository,
        "get_pending_for_order",
        AsyncMock(return_value=_pending_task(_updated_order())),
    )
    create = AsyncMock()
    monkeypatch.setattr(order_service.release_outbox_repository, "create_task", create)

    with pytest.raises(OrderStateConflictError, match="update in progress"):
        await order_service.delete_order_for_requester(_Session(), "order-1", "user-1")

    create.assert_not_awaited()


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
    create = AsyncMock()
    monkeypatch.setattr(order_service.release_outbox_repository, "create_task", create)

    with pytest.raises(OrderStateConflictError):
        await order_service.delete_order_for_requester(_Session(), "order-1", "user-1")

    create.assert_not_awaited()


async def test_delete_translates_database_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        order_service.order_repository,
        "get_order_for_update",
        AsyncMock(side_effect=SQLAlchemyError("database unavailable")),
    )

    with pytest.raises(OrderDeletionError):
        await order_service.delete_order_for_requester(_Session(), "order-1", "user-1")


async def test_delete_does_not_call_credit_when_task_commit_fails(
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
        def begin(self):
            return CommitFailingTransaction()

    monkeypatch.setattr(
        order_service.order_repository,
        "get_order_for_update",
        AsyncMock(return_value=_order()),
    )
    monkeypatch.setattr(
        order_service.update_outbox_repository,
        "get_pending_for_order",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        order_service.release_outbox_repository,
        "create_task",
        AsyncMock(return_value=SimpleNamespace(task_id="task-1")),
    )
    release = AsyncMock()
    _mock_credit_client(monkeypatch, release_credits=release)

    with pytest.raises(OrderDeletionError):
        await order_service.delete_order_for_requester(CommitFailingSession(), "order-1", "user-1")

    release.assert_not_awaited()




async def test_deletion_status_is_only_visible_to_requester(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        order_service.release_outbox_repository,
        "get_task",
        AsyncMock(
            return_value=SimpleNamespace(
                order_id="order-1",
                requester_id="user-1",
                action=ReleaseAction.DELETE,
            )
        ),
    )
    with pytest.raises(OrderAccessDeniedError):
        await order_service.get_deletion_for_requester(_Session(), "task-1", "user-2")


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

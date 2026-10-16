# AI-INFLUENCED: Order database startup initialization test generated with Codex.
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import db
from app.models.order_event_outbox import OrderEventOutbox
from app.models.order_release_tasks import COMPLETED as RELEASE_COMPLETED
from app.models.order_release_tasks import OrderReleaseTask, ReleaseAction
from app.models.order_update_tasks import COMPLETED, OrderUpdateTask
from app.models.orders import OrderTable


async def test_init_db_registers_models_and_creates_missing_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock()
    connection.run_sync = AsyncMock()
    begin_context = MagicMock()
    begin_context.__aenter__ = AsyncMock(return_value=connection)
    begin_context.__aexit__ = AsyncMock(return_value=False)
    engine = MagicMock()
    engine.begin.return_value = begin_context
    monkeypatch.setattr(db, "engine", engine)

    await db.init_db()

    assert OrderTable.__table__ in db.Base.metadata.tables.values()
    assert OrderReleaseTask.__table__ in db.Base.metadata.tables.values()
    assert OrderUpdateTask.__table__ in db.Base.metadata.tables.values()
    assert OrderEventOutbox.__table__ in db.Base.metadata.tables.values()
    connection.run_sync.assert_awaited_once_with(db.Base.metadata.create_all)


def test_only_one_pending_update_can_exist_per_order() -> None:
    engine = create_engine("sqlite://")
    OrderUpdateTask.__table__.create(engine)

    def task() -> OrderUpdateTask:
        return OrderUpdateTask(
            order_id="order-1",
            requester_id="user-1",
            reservation_id="reservation-1",
            proposed_order={"reward": 20},
        )

    with Session(engine) as session:
        first = task()
        session.add(first)
        session.commit()

        session.add(task())
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        first.status = COMPLETED
        session.commit()
        session.add(task())
        session.commit()

    engine.dispose()


def test_only_one_pending_release_action_can_exist_per_reservation() -> None:
    engine = create_engine("sqlite://")
    OrderReleaseTask.__table__.create(engine)

    def task(action: ReleaseAction) -> OrderReleaseTask:
        return OrderReleaseTask(
            order_id="order-1",
            requester_id="requester-1",
            reservation_id="reservation-1",
            action=action.value,
        )

    with Session(engine) as session:
        first = task(ReleaseAction.DELETE)
        session.add(first)
        session.commit()

        session.add(task(ReleaseAction.CANCEL))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        first.status = RELEASE_COMPLETED
        session.commit()
        session.add(task(ReleaseAction.CANCEL))
        session.commit()

    engine.dispose()


def test_event_outbox_migration_can_upgrade_existing_database_and_downgrade():
    path = Path(__file__).parents[1] / "migrations/versions/20261016_order_event_outbox.py"
    spec = importlib.util.spec_from_file_location("event_outbox_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        migration.upgrade()
        columns = {item["name"] for item in inspect(connection).get_columns("order_event_outbox")}
        assert columns == {
            "event_id",
            "payload",
            "published_at",
            "attempts",
            "last_error",
            "created_at",
        }
        migration.downgrade()
        assert "order_event_outbox" not in inspect(connection).get_table_names()
    engine.dispose()


def test_update_outbox_migration_adds_columns_to_existing_table() -> None:
    path = Path(__file__).parents[1] / "migrations/versions/20261016_update_outbox_dispatch.py"
    spec = importlib.util.spec_from_file_location("update_outbox_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE order_update_outbox (task_id VARCHAR(36) PRIMARY KEY)")
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        columns = {item["name"] for item in inspect(connection).get_columns("order_update_outbox")}
        assert "published_at" in columns
    engine.dispose()


def test_release_outbox_migration_creates_generalized_table() -> None:
    path = Path(__file__).parents[1] / "migrations/versions/20261016_order_release_outbox.py"
    spec = importlib.util.spec_from_file_location("release_outbox_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        migration.upgrade()
        columns = {item["name"] for item in inspect(connection).get_columns("order_release_outbox")}
        assert {
            "task_id",
            "order_id",
            "reservation_id",
            "requester_id",
            "action",
            "status",
            "reason",
            "published_at",
        } <= columns
        migration.downgrade()
        assert "order_release_outbox" not in inspect(connection).get_table_names()
    engine.dispose()


def test_release_outbox_migration_preserves_legacy_deletion_tasks() -> None:
    path = Path(__file__).parents[1] / "migrations/versions/20261016_order_release_outbox.py"
    spec = importlib.util.spec_from_file_location("legacy_release_outbox_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE order_deletion_outbox (
                    task_id VARCHAR(36) PRIMARY KEY,
                    order_id VARCHAR NOT NULL UNIQUE,
                    reservation_id VARCHAR(36) NOT NULL,
                    requester_id VARCHAR NOT NULL,
                    status VARCHAR(16) NOT NULL,
                    attempts INTEGER NOT NULL,
                    last_error VARCHAR(500),
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO order_deletion_outbox VALUES (
                    'task-1', 'order-1', 'reservation-1', 'requester-1',
                    'processing', 2, NULL, CURRENT_TIMESTAMP
                )
                """
            )
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        task = connection.execute(
            text(
                "SELECT action, status, attempts FROM order_release_outbox WHERE task_id = 'task-1'"
            )
        ).one()
        assert task == ("delete", "pending", 2)
        assert "order_deletion_outbox" not in inspect(connection).get_table_names()

        connection.execute(
            text("UPDATE order_release_outbox SET status = 'completed' WHERE task_id = 'task-1'")
        )
        connection.execute(
            text(
                """
                INSERT INTO order_release_outbox (
                    task_id, order_id, reservation_id, requester_id, action,
                    status, attempts, created_at
                ) VALUES (
                    'task-2', 'order-1', 'reservation-1', 'requester-1',
                    'cancel', 'pending', 0, CURRENT_TIMESTAMP
                )
                """
            )
        )
    engine.dispose()


def test_single_event_outbox_migration_preserves_pending_publications() -> None:
    versions = Path(__file__).parents[1] / "migrations/versions"

    def load_migration(filename: str, module_name: str):
        spec = importlib.util.spec_from_file_location(module_name, versions / filename)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    event_migration = load_migration(
        "20261016_order_event_outbox.py", "event_outbox_before_task_migration"
    )
    release_migration = load_migration(
        "20261016_order_release_outbox.py", "release_outbox_before_task_migration"
    )
    task_migration = load_migration(
        "20261016_single_order_event_outbox.py", "single_event_outbox_migration"
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        event_migration.op = Operations(context)
        event_migration.upgrade()
        release_migration.op = Operations(context)
        release_migration.upgrade()
        connection.execute(
            text(
                """
                CREATE TABLE order_update_outbox (
                    task_id VARCHAR(36) PRIMARY KEY,
                    order_id VARCHAR NOT NULL,
                    reservation_id VARCHAR(36) NOT NULL,
                    requester_id VARCHAR NOT NULL,
                    proposed_order JSON NOT NULL,
                    status VARCHAR(16) NOT NULL,
                    last_error VARCHAR(500),
                    rejection_code VARCHAR(60),
                    published_at DATETIME,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO order_release_outbox (
                    task_id, order_id, reservation_id, requester_id, action, status,
                    reason, published_at, attempts, created_at
                ) VALUES (
                    'delete-1', 'order-1', 'reservation-1', 'user-1', 'delete',
                    'pending', NULL, NULL, 0, '2026-10-16T10:00:00+00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO order_update_outbox (
                    task_id, order_id, reservation_id, requester_id, proposed_order,
                    status, published_at, attempts, created_at
                ) VALUES (
                    'update-1', 'order-2', 'reservation-2', 'user-2',
                    '{"reward": 42}', 'pending', NULL, 0,
                    '2026-10-16T11:00:00+00:00'
                )
                """
            )
        )

        task_migration.op = Operations(context)
        task_migration.upgrade()

        table_names = set(inspect(connection).get_table_names())
        assert "order_release_outbox" not in table_names
        assert "order_update_outbox" not in table_names
        assert "order_release_tasks" in table_names
        assert "order_update_tasks" in table_names
        release_columns = {
            column["name"] for column in inspect(connection).get_columns("order_release_tasks")
        }
        update_columns = {
            column["name"] for column in inspect(connection).get_columns("order_update_tasks")
        }
        assert "published_at" not in release_columns | update_columns
        assert "attempts" not in release_columns | update_columns

        payloads = (
            connection.execute(text("SELECT payload FROM order_event_outbox")).scalars().all()
        )
        decoded_payloads = [json.loads(payload) for payload in payloads]
        assert len(decoded_payloads) == 2
        assert {payload["event_type"] for payload in decoded_payloads} == {
            "OrderDeletionRequested",
            "OrderUpdate",
        }
        assert {payload["task_id"] for payload in decoded_payloads} == {
            "delete-1",
            "update-1",
        }
    engine.dispose()

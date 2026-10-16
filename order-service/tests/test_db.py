# AI-INFLUENCED: Order database startup initialization test generated with Codex.
from __future__ import annotations

import importlib.util
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
from app.models.order_release_outbox import COMPLETED as RELEASE_COMPLETED
from app.models.order_release_outbox import OrderReleaseOutbox, ReleaseAction
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
    assert OrderReleaseOutbox.__table__ in db.Base.metadata.tables.values()
    assert OrderEventOutbox.__table__ in db.Base.metadata.tables.values()
    connection.run_sync.assert_awaited_once_with(db.Base.metadata.create_all)




def test_only_one_pending_release_action_can_exist_per_reservation() -> None:
    engine = create_engine("sqlite://")
    OrderReleaseOutbox.__table__.create(engine)

    def task(action: ReleaseAction) -> OrderReleaseOutbox:
        return OrderReleaseOutbox(
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

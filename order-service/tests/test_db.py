# AI-INFLUENCED: Order database startup initialization test generated with Codex.
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from app import db
from app.models.order_event_outbox import OrderEventOutbox
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
    assert OrderEventOutbox.__table__ in db.Base.metadata.tables.values()
    connection.run_sync.assert_awaited_once_with(db.Base.metadata.create_all)


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

# AI-INFLUENCED: Order database startup initialization test generated with Codex.
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app import db
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
    connection.run_sync.assert_awaited_once_with(db.Base.metadata.create_all)

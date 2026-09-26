from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base, get_session
from app.main import app
from app.services import events


@pytest.fixture(autouse=True)
def _test_db(tmp_path):
    """Point get_session at a fresh sqlite file per test instead of Postgres.

    Schema is created with a plain sync engine (DDL doesn't need async), so
    there's no event-loop-affinity issue with the async sqlite driver.
    """
    db_file = tmp_path / "test.db"

    sync_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    TestSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)

    async def _override_get_session():
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _no_real_rabbitmq(monkeypatch):
    # Registration/verification must not depend on a live broker in tests.
    monkeypatch.setattr(events, "publish_user_registered", AsyncMock())
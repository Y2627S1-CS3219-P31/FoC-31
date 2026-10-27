# AI-INFLUENCED: Optional isolated PostgreSQL integration fixtures added with Codex.
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base


def pytest_addoption(parser):
    parser.addoption("--postgres-url", help="Asyncpg URL for optional PostgreSQL integration tests")


@pytest.fixture
async def postgres_sessions(request):
    url = request.config.getoption("--postgres-url")
    if not url:
        pytest.skip("Pass --postgres-url to run PostgreSQL integration tests")
    # Never create or drop application tables in the supplied database's public schema.
    schema = f"order_test_{uuid4().hex}"
    admin_engine = create_async_engine(url)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()

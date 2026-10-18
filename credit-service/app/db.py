from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def pool_stats() -> dict[str, int]:
    """Current SQLAlchemy pool occupancy (saturation shows up here first)."""
    pool = getattr(engine.sync_engine, "pool", None)
    if pool is None:
        return {"in_use": 0, "size": 0, "overflow": 0}
    try:
        return {
            "in_use": pool.checkedout(),
            "size": pool.size(),
            # QueuePool keeps a signed overflow counter (negative while the pool
            # is under-utilised); clamp it so the gauge reads as "extra
            # connections in use", never negative.
            "overflow": max(pool.overflow(), 0),
        }
    except (AttributeError, NotImplementedError):
        # Non-pooled/static pool implementations do not expose these counters.
        return {"in_use": 0, "size": 0, "overflow": 0}

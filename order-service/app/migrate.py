from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.db import engine

_PENULTIMATE_REVISION = "20261019_supplier_deactivation_inbox"


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    return cfg


def _prepare_and_inspect(connection) -> tuple[bool, bool, bool]:
    inspector = inspect(connection)
    if inspector.has_table("alembic_version"):
        # Revision ids in this repo exceed Alembic's default version_num
        # VARCHAR(32); widen it so stamping and upgrades can record them.
        connection.execute(
            text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)")
        )
        adopted = (
            connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
            is not None
        )
    else:
        connection.execute(
            text(
                "CREATE TABLE alembic_version ("
                "version_num VARCHAR(255) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            )
        )
        adopted = False

    has_orders = inspector.has_table("orders")
    has_column = has_orders and any(
        column["name"] == "proof_of_delivery_photo_key"
        for column in inspector.get_columns("orders")
    )
    return adopted, has_orders, has_column


def _apply(stamp_revision: str | None) -> None:
    cfg = _alembic_config()
    if stamp_revision is not None:
        command.stamp(cfg, stamp_revision)
    command.upgrade(cfg, "head")


async def run_migrations() -> None:
    async with engine.begin() as connection:
        adopted, has_orders, has_column = await connection.run_sync(_prepare_and_inspect)

    stamp_revision: str | None = None
    if not adopted:
        if has_column:
            stamp_revision = "head"
        elif has_orders:
            stamp_revision = _PENULTIMATE_REVISION

    # Alembic's env.py drives the async engine via asyncio.run(); run it off the
    # lifespan event loop so the two loops do not collide.
    await asyncio.to_thread(_apply, stamp_revision)

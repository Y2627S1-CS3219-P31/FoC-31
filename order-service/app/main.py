# AI-INFLUENCED: Centralized API exception registration added with Codex.
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.error_handlers import register_exception_handlers
from app.api.routes import health, orders
from app.db import engine, init_db
from app.services.client_manager import (
    _start_remote_clients,
    close_remote_clients,
)
from app.services.event_worker import run_event_worker
from app.services.expiry_worker import run_expiry_sweeper
from app.services.release_consumer import run_release_consumer
from app.services.update_consumer import run_update_consumer


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    _start_remote_clients()
    release_consumer_task = asyncio.create_task(run_release_consumer())
    update_consumer_task = asyncio.create_task(run_update_consumer())
    event_worker_task = asyncio.create_task(run_event_worker())
    expiry_sweeper_task = asyncio.create_task(run_expiry_sweeper())
    try:
        yield
    finally:
        release_consumer_task.cancel()
        update_consumer_task.cancel()
        event_worker_task.cancel()
        expiry_sweeper_task.cancel()
        with suppress(asyncio.CancelledError):
            await release_consumer_task
        with suppress(asyncio.CancelledError):
            await update_consumer_task
        with suppress(asyncio.CancelledError):
            await event_worker_task
        with suppress(asyncio.CancelledError):
            await expiry_sweeper_task
        await close_remote_clients()
        await engine.dispose()


app = FastAPI(
    title="FoC Order Service",
    version="0.1.0",
    lifespan=lifespan,
)
register_exception_handlers(app)
app.include_router(health.router)
app.include_router(orders.router)

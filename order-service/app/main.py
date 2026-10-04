# AI-INFLUENCED: Centralized API exception registration added with Codex.
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.error_handlers import register_exception_handlers
from app.api.routes import health, orders
from app.db import engine, init_db
from app.services.client_manager import (
    _start_remote_clients,
    close_remote_clients,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    _start_remote_clients()
    try:
        yield
    finally:
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

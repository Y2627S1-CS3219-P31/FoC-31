# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health, users
from app.bootstrap import seed_bootstrap_admin
from app.config import settings
from app.db import engine, get_session, init_db
from app.observability import OBS
from app.services.events import outbox_worker
from foc_shared.observability import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    await init_db()
    await seed_bootstrap_admin()
    worker = asyncio.create_task(outbox_worker())
    try:
        yield
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await engine.dispose()


app = FastAPI(title="FoC User Service", version="0.1.0", lifespan=lifespan)
# Shared observability: /metrics, /health/ready, HTTP metrics, request ids.
# check_broker=False: this service publishes through an outbox and keeps no
# consumer connection, so broker state would always read "unavailable".
OBS.install(app, readiness_session_dep=get_session, check_broker=False)
app.include_router(health.router)
app.include_router(users.router)

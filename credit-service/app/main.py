# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.routes import credits, health
from app.db import init_db
from app.errors import register_exception_handlers
from app.services.consumer import CreditEventConsumer


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    consumer_task = asyncio.create_task(CreditEventConsumer().run())
    yield
    consumer_task.cancel()
    with suppress(asyncio.CancelledError):
        await consumer_task


app = FastAPI(title="FoC Credit Service", version="0.1.0", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(health.router)
app.include_router(credits.router)

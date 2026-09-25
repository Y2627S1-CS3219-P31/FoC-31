from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health, suppliers
from app.db import init_db
from app.errors import register_exception_handlers


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(title="FoC Supplier Service", version="0.1.0", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(health.router)
app.include_router(suppliers.router)

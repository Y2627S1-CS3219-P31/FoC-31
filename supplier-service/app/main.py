# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health, suppliers
from app.config import settings
from app.db import get_session, init_db
from app.errors import register_exception_handlers
from app.observability import OBS
from app.services.seeder import SEED_CSV_PATH, seed_suppliers
from foc_shared.observability import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    await init_db()
    if SEED_CSV_PATH.exists():
        inserted = await seed_suppliers()
        logger.info("Supplier seeder inserted %d new row(s).", inserted)
    else:
        logger.warning("Seed CSV not found at %s; skipping startup seed.", SEED_CSV_PATH)
    yield


app = FastAPI(title="FoC Supplier Service", version="0.1.0", lifespan=lifespan)
# Shared observability: /metrics, /health/ready, HTTP + error-code metrics.
OBS.install(app, readiness_session_dep=get_session)
register_exception_handlers(app)
app.include_router(health.router)
app.include_router(suppliers.router)

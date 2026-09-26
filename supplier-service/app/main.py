from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health, suppliers
from app.db import init_db
from app.errors import register_exception_handlers
from app.services.seeder import SEED_CSV_PATH, seed_suppliers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    if SEED_CSV_PATH.exists():
        inserted = await seed_suppliers()
        logger.info("Supplier seeder inserted %d new row(s).", inserted)
    else:
        logger.warning(
            "Seed CSV not found at %s; skipping startup seed.", SEED_CSV_PATH
        )
    yield


app = FastAPI(title="FoC Supplier Service", version="0.1.0", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(health.router)
app.include_router(suppliers.router)

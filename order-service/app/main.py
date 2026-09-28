# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.routes import health, orders
from app.clients.credits import CreditClient
from app.clients.suppliers import SupplierClient
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with httpx.AsyncClient(timeout=5.0) as http_client:
        app.state.supplier_client = SupplierClient(
            http_client,
            settings.supplier_service_url,
        )
        app.state.credit_client = CreditClient(
            http_client,
            settings.credit_service_url,
        )
        yield


app = FastAPI(title="FoC Order Service", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(orders.router)

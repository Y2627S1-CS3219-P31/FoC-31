from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import health, orders

app = FastAPI(title="FoC Order Service", version="0.1.0")
app.include_router(health.router)
app.include_router(orders.router)

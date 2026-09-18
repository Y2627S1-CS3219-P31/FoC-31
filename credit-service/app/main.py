from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import credits, health

app = FastAPI(title="FoC Credit Service", version="0.1.0")
app.include_router(health.router)
app.include_router(credits.router)

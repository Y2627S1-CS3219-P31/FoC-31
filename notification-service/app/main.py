from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import health, notifications

app = FastAPI(title="FoC Notification Service", version="0.1.0")
app.include_router(health.router)
app.include_router(notifications.router)

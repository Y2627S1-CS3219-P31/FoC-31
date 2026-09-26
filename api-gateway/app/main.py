from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, proxy
from app.config import settings

app = FastAPI(title="FoC API Gateway", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() 
                   for origin in settings.cors_allowed_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(proxy.router)

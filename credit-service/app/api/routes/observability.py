# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Prometheus exposition plus the readiness probe.

``GET /health`` stays exactly as the root AGENTS.md requires
(``{"status": "ok"}`` and nothing else); readiness is a separate endpoint so the
container healthcheck semantics do not change.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.observability import health as broker_health
from app.observability import metrics

logger = logging.getLogger(__name__)

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    """Scraped by Prometheus inside the compose network (never via the gateway)."""
    return Response(content=metrics.render(), media_type=CONTENT_TYPE_LATEST)


@router.get("/health/ready")
async def readiness(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """Liveness of the things credit-service cannot work without: DB + broker."""
    checks: dict[str, str] = {}
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        logger.exception("Readiness probe: database check failed.")
        checks["database"] = "unavailable"

    broker = broker_health.broker_state()
    checks["broker"] = "ok" if broker["connected"] else "unavailable"
    ready = all(value == "ok" for value in checks.values())

    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "degraded",
            "checks": checks,
            "broker_error": broker["error"],
            "uptime_seconds": round(time.time() - metrics.STARTED_AT, 3),
        },
    )

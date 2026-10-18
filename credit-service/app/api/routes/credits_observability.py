# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Read-only observability view of the credit service (admin only).

Kept separate from ``/metrics``: Prometheus scrapes the container directly,
while this JSON endpoint is meant for humans/humans-in-a-demo going through the
API gateway (``GET /api/credits/observability/summary``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import AdminDep, get_credit_service
from app.observability.summary import build_summary
from app.services.credit_service import CreditService

router = APIRouter(prefix="/credits/observability", tags=["observability"])

ServiceDep = Annotated[CreditService, Depends(get_credit_service)]


@router.get("/summary")
async def summary(identity: AdminDep, service: ServiceDep) -> dict[str, object]:
    """One JSON block: availability, latency, business errors, saga, broker health."""
    return await build_summary(service)

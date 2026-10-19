# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""HTTP instrumentation middleware.

Records one sample per handled request, labelled by the *route template* (read
from ``scope["route"]`` after routing, so raw ids never leak into labels), and
propagates an ``X-Request-Id`` that the structured logs carry.

Error-envelope ``code`` labels are recorded by the exception handlers in
``app/errors.py`` instead: they already know the business code and this way the
middleware never has to parse a response body.

``/metrics`` and the health endpoints are excluded so scrape traffic and docker
healthchecks cannot distort QPS or availability numbers.
"""

from __future__ import annotations

import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.observability import context, metrics
from foc_shared.auth import HEADER_USER_ID

EXCLUDED_PATHS = frozenset(
    {
        # Operational endpoints: scrape + probes must not distort QPS/availability.
        "/metrics",
        "/health",
        "/health/ready",
        # Framework endpoints, not business traffic.
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        request_id = request.headers.get("x-request-id") or uuid4().hex
        token = context.bind(
            request_id=request_id,
            user_id=request.headers.get(HEADER_USER_ID),
        )

        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            metrics.observe_http_request(
                method=request.method,
                route=metrics.route_template(request.scope),
                status=str(status),
                duration=time.perf_counter() - started,
            )
            context.reset(token)

        response.headers["X-Request-Id"] = request_id
        return response

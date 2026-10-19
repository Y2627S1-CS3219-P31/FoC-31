# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Shared observability layer for the FoC backend services.

One implementation, one set of conventions, installed per service:

```python
from foc_shared.observability import Observability

obs = Observability("credit-service", prefix="credit")
obs.install(app, readiness_session_dep=get_session)
```

What a service gets:

- ``GET /metrics`` - Prometheus exposition from its own registry
- ``GET /health/ready`` - database (when a session dependency is given) and
  broker readiness; ``GET /health`` is left untouched
- HTTP request/latency/status metrics labelled by **route template** and by
  ``service``, so one Grafana dashboard can compare services
- error-envelope ``code`` counters (call ``record_error_code`` from the service
  exception handlers, which are the only layer that knows the code)
- JSON log formatting with ``request_id`` / ``user_id`` / ``order_id`` /
  ``task_id`` correlation
- broker connection state shared with readiness
- query helpers used by a service's own JSON summary endpoint

Design notes:

- Every service owns a :class:`CollectorRegistry`; nothing is global, so two
  services (or two test apps) can coexist in one process.
- Metric names are prefixed with ``prefix``; business metrics a service adds via
  :meth:`Observability.counter` live in the same registry and are discovered by
  ``/metrics`` automatically.
- ``/metrics`` and the health endpoints are excluded from the HTTP metrics so
  probes and scrapes never distort QPS or availability.
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Callable, Iterable
from contextvars import ContextVar, Token
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from foc_shared.auth import HEADER_USER_ID

__all__ = [
    "DEFAULT_EXCLUDED_PATHS",
    "Observability",
    "ObservabilityMiddleware",
    "bind",
    "broker_state",
    "configure_logging",
    "context",
    "current",
    "reset",
    "set_broker_state",
]

DEFAULT_EXCLUDED_PATHS: frozenset[str] = frozenset(
    {
        # Operational endpoints: scrape + probes must not distort the numbers.
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

HTTP_BUCKETS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

_STARTED_AT = time.time()

# ── log context ──────────────────────────────────────────────────────────────

_LOG_CONTEXT: ContextVar[dict[str, str] | None] = ContextVar("foc_log_context", default=None)


def bind(**values: str | None) -> Token:
    """Merge non-empty ``values`` into the current task/thread log context."""
    merged = {**(_LOG_CONTEXT.get() or {}), **{k: v for k, v in values.items() if v}}
    return _LOG_CONTEXT.set(merged)


def reset(token: Token) -> None:
    _LOG_CONTEXT.reset(token)


def current() -> dict[str, str]:
    return dict(_LOG_CONTEXT.get() or {})


class _ContextProxy:
    """``from foc_shared.observability import context`` convenience namespace."""

    bind = staticmethod(bind)
    reset = staticmethod(reset)
    current = staticmethod(current)


context = _ContextProxy()

# ── broker state ─────────────────────────────────────────────────────────────

_broker: dict[str, object] = {"connected": False, "error": None, "changed_at": None}


def set_broker_state(connected: bool, error: str | None = None) -> None:
    _broker["connected"] = connected
    _broker["error"] = error
    _broker["changed_at"] = time.time()


def broker_state() -> dict[str, object]:
    return dict(_broker)


# ── structured logging ───────────────────────────────────────────────────────

_PROMOTED_EXTRA_KEYS = (
    "order_id",
    "task_id",
    "user_id",
    "queue",
    "routing_key",
    "event_type",
    "outcome",
    "code",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(current())
        for key in _PROMOTED_EXTRA_KEYS:
            value = record.__dict__.get(key)
            if value:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        stamp = time.strftime("%H:%M:%S", time.localtime(record.created))
        extra = " ".join(f"{k}={v}" for k, v in current().items())
        line = f"{stamp} {record.levelname:<7} {record.name}: {record.getMessage()}"
        if extra:
            line = f"{line} [{extra}]"
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def configure_logging(
    *, level: str = "info", json_output: bool = False, logger_name: str = "app"
) -> None:
    """Attach one handler to ``logger_name`` (idempotent; uvicorn untouched)."""
    resolved = getattr(logging, level.upper(), logging.INFO)
    logger = logging.getLogger(logger_name)
    logger.setLevel(resolved)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if json_output else TextFormatter())
    logger.addHandler(handler)
    # Root never sees these records, so uvicorn's own output stays as configured.
    logger.propagate = False


# ── HTTP instrumentation ─────────────────────────────────────────────────────


class Observability:
    """Per-service metrics registry, HTTP instrumentation and readiness."""

    def __init__(
        self,
        service: str,
        *,
        prefix: str | None = None,
        excluded_paths: Iterable[str] | None = None,
    ) -> None:
        self.service = service
        self.prefix = prefix or service.replace("-service", "").replace("-", "_")
        self.excluded_paths = frozenset(excluded_paths or DEFAULT_EXCLUDED_PATHS)
        self.started_at = _STARTED_AT
        self.registry = CollectorRegistry(auto_describe=False)

        self.http_requests = Counter(
            f"{self.prefix}_http_requests_total",
            "HTTP requests handled by the service.",
            ["service", "method", "route", "status"],
            registry=self.registry,
        )
        self.http_duration = Histogram(
            f"{self.prefix}_http_request_duration_seconds",
            "HTTP request latency observed by the service.",
            ["service", "method", "route", "status"],
            buckets=HTTP_BUCKETS,
            registry=self.registry,
        )
        self.http_errors = Counter(
            f"{self.prefix}_http_errors_total",
            "Error responses by error-envelope code.",
            ["service", "route", "code"],
            registry=self.registry,
        )

    # ── service-specific metrics ─────────────────────────────────────────────

    def counter(self, name: str, documentation: str, labels: Iterable[str] = ()) -> Counter:
        return Counter(name, documentation, list(labels), registry=self.registry)

    def histogram(
        self,
        name: str,
        documentation: str,
        labels: Iterable[str] = (),
        *,
        buckets: Iterable[float] = HTTP_BUCKETS,
    ) -> Histogram:
        return Histogram(
            name, documentation, list(labels), buckets=tuple(buckets), registry=self.registry
        )

    def gauge(self, name: str, documentation: str, labels: Iterable[str] = ()) -> Gauge:
        return Gauge(name, documentation, list(labels), registry=self.registry)

    # ── recording ────────────────────────────────────────────────────────────

    @staticmethod
    def route_template(scope: dict) -> str:
        """The matched route template, or ``<unmatched>`` (bounded cardinality)."""
        route = scope.get("route")
        return getattr(route, "path", None) or "<unmatched>"

    def observe_http_request(
        self, *, method: str, route: str, status: str, duration: float
    ) -> None:
        self.http_requests.labels(
            service=self.service, method=method, route=route, status=status
        ).inc()
        self.http_duration.labels(
            service=self.service, method=method, route=route, status=status
        ).observe(duration)

    def record_error_code(self, route: str, code: str) -> None:
        self.http_errors.labels(service=self.service, route=route, code=code).inc()

    # ── exposition / queries ────────────────────────────────────────────────

    def render(self) -> bytes:
        return generate_latest(self.registry)

    def exposed_metrics(self) -> list[str]:
        """Every metric family name exposed at ``/metrics`` (sorted)."""
        return sorted(family.name for family in self.registry.collect())

    @staticmethod
    def value(metric, **labels: str) -> float:
        base = getattr(metric, "_name", "")
        wanted = {base, f"{base}_total"}
        total = 0.0
        for family in metric.collect():
            for sample in family.samples:
                if sample.name not in wanted:
                    continue
                if all(sample.labels.get(k) == v for k, v in labels.items()):
                    total += sample.value
        return total

    @staticmethod
    def table(metric) -> list[dict[str, object]]:
        base = getattr(metric, "_name", "")
        wanted = {base, f"{base}_total"}
        rows: list[dict[str, object]] = []
        for family in metric.collect():
            for sample in family.samples:
                if sample.name not in wanted:
                    continue
                row: dict[str, object] = dict(sample.labels)
                row["value"] = sample.value
                rows.append(row)
        return rows

    @staticmethod
    def table_to_map(metric, key: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in Observability.table(metric):
            label = str(row.get(key, "unknown"))
            out[label] = out.get(label, 0) + int(row["value"])
        return out

    @staticmethod
    def _buckets(metric, **match: str) -> dict[float, float]:
        base = getattr(metric, "_name", "")
        bucket_name = f"{base}_bucket"
        out: dict[float, float] = {}
        for family in metric.collect():
            for sample in family.samples:
                if sample.name != bucket_name:
                    continue
                if not all(sample.labels.get(k) == v for k, v in match.items()):
                    continue
                le = sample.labels.get("le")
                if le is None:
                    continue
                bound = float(le)
                out[bound] = out.get(bound, 0.0) + sample.value
        return out

    @staticmethod
    def _count_and_sum(metric, **match: str) -> tuple[float, float]:
        base = getattr(metric, "_name", "")
        count = total = 0.0
        for family in metric.collect():
            for sample in family.samples:
                if sample.name not in (f"{base}_count", f"{base}_sum"):
                    continue
                if not all(sample.labels.get(k) == v for k, v in match.items()):
                    continue
                if sample.name.endswith("_count"):
                    count += sample.value
                else:
                    total += sample.value
        return count, total

    @staticmethod
    def percentile(buckets: dict[float, float], quantile: float) -> float | None:
        total = buckets.get(math.inf, 0.0)
        if total <= 0:
            return None
        bounds = sorted(bound for bound in buckets if not math.isinf(bound))
        if not bounds:
            return None
        target = quantile * total
        lower_bound, lower_count = 0.0, 0.0
        for bound in bounds:
            cumulative = buckets[bound]
            if cumulative >= target:
                span = bound - lower_bound
                in_bucket = cumulative - lower_count
                if in_bucket <= 0:
                    return round(bound, 6)
                return round(lower_bound + span * (target - lower_count) / in_bucket, 6)
            lower_bound, lower_count = bound, cumulative
        return round(bounds[-1], 6)

    @classmethod
    def histogram_stats(cls, metric, **match: str) -> dict[str, float | None]:
        count, total = cls._count_and_sum(metric, **match)
        buckets = cls._buckets(metric, **match)
        return {
            "count": count,
            "sum_seconds": round(total, 6),
            "mean_seconds": round(total / count, 6) if count else None,
            "p50_seconds": cls.percentile(buckets, 0.50),
            "p95_seconds": cls.percentile(buckets, 0.95),
            "p99_seconds": cls.percentile(buckets, 0.99),
        }

    def http_summary(self) -> dict[str, object]:
        by_class = {"2xx": 0.0, "3xx": 0.0, "4xx": 0.0, "5xx": 0.0, "other": 0.0}
        per_route: dict[tuple[str, str], dict[str, float]] = {}
        failures = 0.0
        for row in self.table(self.http_requests):
            value = float(row["value"])
            status = str(row.get("status", ""))
            key = status[:1] + "xx" if status[:1] in "2345" else "other"
            by_class[key] = by_class.get(key, 0.0) + value
            if status[:1] == "5":
                failures += value
            route_key = (str(row.get("method", "?")), str(row.get("route", "<unmatched>")))
            entry = per_route.setdefault(route_key, {"requests": 0.0, "error_responses": 0.0})
            entry["requests"] += value
            if status[:1] in {"4", "5"}:
                entry["error_responses"] += value

        total = sum(by_class.values())
        routes = []
        for (method, route), counts in per_route.items():
            stats = self.histogram_stats(self.http_duration, method=method, route=route)
            routes.append(
                {
                    "method": method,
                    "route": route,
                    "requests": int(counts["requests"]),
                    "error_responses": int(counts["error_responses"]),
                    "p95_seconds": stats["p95_seconds"],
                }
            )
        routes.sort(key=lambda item: item["requests"], reverse=True)
        overall = self.histogram_stats(self.http_duration)
        return {
            "total_requests": int(total),
            "requests_by_class": {k: int(v) for k, v in by_class.items() if v or k != "other"},
            "server_error_rate": round(failures / total, 6) if total else 0.0,
            "availability": round(1 - failures / total, 6) if total else None,
            "latency_seconds": {
                "p50": overall["p50_seconds"],
                "p95": overall["p95_seconds"],
                "p99": overall["p99_seconds"],
                "mean": overall["mean_seconds"],
            },
            "routes": routes,
        }

    # ── installation ────────────────────────────────────────────────────────

    def install(
        self,
        app: FastAPI,
        *,
        readiness_session_dep: Callable | None = None,
        readiness_extra: Callable[[], dict[str, str]] | None = None,
        check_broker: bool = True,
    ) -> None:
        """Mount ``/metrics`` and ``/health/ready`` and add the middleware.

        ``check_broker`` should stay ``True`` only for a service that keeps
        :func:`set_broker_state` up to date (a long-lived consumer). Services
        that merely publish through an outbox, or do not use the broker at all,
        would otherwise report ``degraded`` forever.
        """
        app.add_middleware(ObservabilityMiddleware, observability=self)
        app.include_router(self._metrics_router())
        app.include_router(
            self._readiness_router(readiness_session_dep, readiness_extra, check_broker)
        )

    def _metrics_router(self) -> APIRouter:
        router = APIRouter(tags=["observability"])

        @router.get("/metrics", include_in_schema=False)
        async def prometheus_metrics() -> Response:
            return Response(content=self.render(), media_type=CONTENT_TYPE_LATEST)

        return router

    def _readiness_router(
        self,
        session_dep: Callable | None,
        extra: Callable[[], dict[str, str]] | None,
        check_broker: bool,
    ) -> APIRouter:
        router = APIRouter(tags=["observability"])

        async def _payload(session) -> tuple[int, dict[str, object]]:
            checks: dict[str, str] = {}
            if session is not None:
                try:
                    await session.execute(text("SELECT 1"))
                    checks["database"] = "ok"
                except Exception:
                    logging.getLogger("app").exception("Readiness: database check failed.")
                    checks["database"] = "unavailable"
            if extra is not None:
                try:
                    checks.update(extra())
                except Exception:
                    logging.getLogger("app").exception("Readiness: extra check failed.")
            broker = broker_state()
            if check_broker:
                checks["broker"] = "ok" if broker["connected"] else "unavailable"
            ready = all(value == "ok" for value in checks.values())
            return (
                200 if ready else 503,
                {
                    "status": "ready" if ready else "degraded",
                    "checks": checks,
                    "broker_error": broker["error"] if check_broker else None,
                    "uptime_seconds": round(time.time() - self.started_at, 3),
                },
            )

        if session_dep is None:

            @router.get("/health/ready")
            async def readiness() -> JSONResponse:
                status, payload = await _payload(None)
                return JSONResponse(status_code=status, content=payload)

        else:

            @router.get("/health/ready")
            async def readiness(
                session=Depends(session_dep),  # noqa: B008 - chosen at install time
            ) -> JSONResponse:
                status, payload = await _payload(session)
                return JSONResponse(status_code=status, content=payload)

        return router


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Records one HTTP sample per request and propagates ``X-Request-Id``."""

    def __init__(self, app, *, observability: Observability) -> None:
        super().__init__(app)
        self.obs = observability

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self.obs.excluded_paths:
            return await call_next(request)

        request_id = request.headers.get("x-request-id") or uuid4().hex
        token = bind(request_id=request_id, user_id=request.headers.get(HEADER_USER_ID))

        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            self.obs.observe_http_request(
                method=request.method,
                route=self.obs.route_template(request.scope),
                status=str(status),
                duration=time.perf_counter() - started,
            )
            reset(token)

        response.headers["X-Request-Id"] = request_id
        return response

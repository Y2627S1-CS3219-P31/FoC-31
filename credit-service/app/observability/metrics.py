# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Prometheus metrics for credit-service.

Three families, each with a distinct consumer:

- **HTTP** (``credit_http_*``): request count, latency and the error-envelope
  ``code``. Latency is labelled by the *route template*
  (``/credits/{user_id}/balance``) so the series count stays bounded.
- **business** (``credit_reservation_ops_total``, ...): what the credit domain
  actually did — including saga rejections that never reach HTTP because they
  travel over RabbitMQ.
- **integration** (``credit_event_publish_*``, ``credit_consumer_*``,
  ``credit_db_pool_*``): is the async path and the database healthy?

A dedicated registry (not the prometheus_client default one) keeps the
exposition text limited to what this service actually instruments.
"""

from __future__ import annotations

import math
import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

REGISTRY = CollectorRegistry()
STARTED_AT = time.time()

_HTTP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_PUBLISH_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0, 3.0, 5.0)

# ── HTTP ──────────────────────────────────────────────────────────────────────

HTTP_REQUESTS = Counter(
    "credit_http_requests_total",
    "HTTP requests handled by the credit service.",
    ["method", "route", "status"],
    registry=REGISTRY,
)

HTTP_DURATION = Histogram(
    "credit_http_request_duration_seconds",
    "HTTP request latency observed by the credit service.",
    ["method", "route", "status"],
    buckets=_HTTP_BUCKETS,
    registry=REGISTRY,
)

HTTP_ERRORS = Counter(
    "credit_http_errors_total",
    "Error responses by error-envelope code (app/errors.py).",
    ["route", "code"],
    registry=REGISTRY,
)

# ── Business operations ───────────────────────────────────────────────────────

RESERVATION_OPS = Counter(
    "credit_reservation_ops_total",
    "Reserve attempts by outcome.",
    ["outcome"],
    registry=REGISTRY,
)

AMENDMENT_OPS = Counter(
    "credit_amendment_ops_total",
    "Reservation amendments by outcome.",
    ["outcome"],
    registry=REGISTRY,
)

TRANSFER_OPS = Counter(
    "credit_transfer_ops_total",
    "Settlements to a courier by outcome.",
    ["outcome"],
    registry=REGISTRY,
)

RELEASE_OPS = Counter(
    "credit_release_ops_total",
    "Reservation releases by outcome.",
    ["outcome"],
    registry=REGISTRY,
)

DUPLICATE_SUPPRESSED = Counter(
    "credit_duplicate_suppressed_total",
    "Operations that would have applied twice but were suppressed as duplicates.",
    ["op"],
    registry=REGISTRY,
)

SAGA_TASKS = Counter(
    "credit_saga_tasks_total",
    "Order Service task outcomes (release / amend).",
    ["kind", "outcome"],
    registry=REGISTRY,
)

SAGA_RETRIES_EXHAUSTED = Counter(
    "credit_saga_retries_exhausted_total",
    "Order Service tasks that used up the retry budget before answering.",
    ["kind"],
    registry=REGISTRY,
)

# ── Event integration (RabbitMQ) ──────────────────────────────────────────────

EVENT_PUBLISH = Counter(
    "credit_event_publish_total",
    "Events published to foc.credit.events by routing key and result.",
    ["routing_key", "result"],
    registry=REGISTRY,
)

EVENT_PUBLISH_DURATION = Histogram(
    "credit_event_publish_duration_seconds",
    "Time spent publishing one event (connection setup included).",
    ["routing_key"],
    buckets=_PUBLISH_BUCKETS,
    registry=REGISTRY,
)

CONSUMER_MESSAGES = Counter(
    "credit_consumer_messages_total",
    "Consumed messages by queue and handling result.",
    ["queue", "result"],
    registry=REGISTRY,
)

CONSUMER_REQUEUES = Counter(
    "credit_consumer_requeues_total",
    "Consumer retry/requeue decisions by queue and reason.",
    ["queue", "reason"],
    registry=REGISTRY,
)

CONSUMER_LAST_MESSAGE = Gauge(
    "credit_consumer_last_message_unixtime",
    "Unix time of the last message handled per queue (staleness signal).",
    ["queue"],
    registry=REGISTRY,
)

CONSUMER_CONNECTED = Gauge(
    "credit_consumer_connected",
    "1 when the consumer holds a live connection for the queue.",
    ["queue"],
    registry=REGISTRY,
)

# ── Resources ─────────────────────────────────────────────────────────────────

DB_POOL_IN_USE = Gauge(
    "credit_db_pool_in_use", "Database connections currently checked out.", registry=REGISTRY
)
DB_POOL_SIZE = Gauge("credit_db_pool_size", "Configured database pool size.", registry=REGISTRY)
DB_POOL_OVERFLOW = Gauge(
    "credit_db_pool_overflow", "Database connections open beyond the pool size.", registry=REGISTRY
)
RESERVED_BALANCE_SUM = Gauge(
    "credit_reserved_balance_sum",
    "Credits currently held in reservations across all accounts.",
    registry=REGISTRY,
)
AVAILABLE_BALANCE_SUM = Gauge(
    "credit_available_balance_sum",
    "Credits currently spendable across all accounts.",
    registry=REGISTRY,
)
ACCOUNTS_TOTAL = Gauge("credit_accounts_total", "Credit accounts provisioned.", registry=REGISTRY)


# ── Recording helpers ─────────────────────────────────────────────────────────


def route_template(scope: dict) -> str:
    """The matched route template, or ``<unmatched>``.

    Using the template (``/credits/{user_id}/balance``) instead of the raw path
    is what keeps label cardinality bounded: arbitrary ``user_id`` values never
    become a new time series.
    """
    route = scope.get("route")
    return getattr(route, "path", None) or "<unmatched>"


def observe_http_request(*, method: str, route: str, status: str, duration: float) -> None:
    HTTP_REQUESTS.labels(method=method, route=route, status=status).inc()
    HTTP_DURATION.labels(method=method, route=route, status=status).observe(duration)


def record_error_code(route: str, code: str) -> None:
    HTTP_ERRORS.labels(route=route, code=code).inc()


def record_reservation(outcome: str) -> None:
    RESERVATION_OPS.labels(outcome=outcome).inc()


def record_amendment(outcome: str) -> None:
    AMENDMENT_OPS.labels(outcome=outcome).inc()


def record_transfer(outcome: str) -> None:
    TRANSFER_OPS.labels(outcome=outcome).inc()


def record_release(outcome: str) -> None:
    RELEASE_OPS.labels(outcome=outcome).inc()


def record_duplicate_suppressed(op: str) -> None:
    DUPLICATE_SUPPRESSED.labels(op=op).inc()


def record_saga_task(kind: str, outcome: str) -> None:
    SAGA_TASKS.labels(kind=kind, outcome=outcome).inc()


def record_saga_retries_exhausted(kind: str) -> None:
    SAGA_RETRIES_EXHAUSTED.labels(kind=kind).inc()


def record_event_publish(routing_key: str, *, ok: bool, duration: float) -> None:
    EVENT_PUBLISH.labels(routing_key=routing_key, result="ok" if ok else "failed").inc()
    EVENT_PUBLISH_DURATION.labels(routing_key=routing_key).observe(duration)


def record_consumer_message(queue: str, result: str) -> None:
    CONSUMER_MESSAGES.labels(queue=queue, result=result).inc()


def mark_consumer_message(queue: str) -> None:
    CONSUMER_LAST_MESSAGE.labels(queue=queue).set(time.time())


def set_consumer_connected(queue: str, connected: bool) -> None:
    CONSUMER_CONNECTED.labels(queue=queue).set(1 if connected else 0)


def record_consumer_requeue(queue: str, reason: str) -> None:
    CONSUMER_REQUEUES.labels(queue=queue, reason=reason).inc()


def set_pool_gauges(stats: dict[str, int]) -> None:
    DB_POOL_IN_USE.set(stats.get("in_use", 0))
    DB_POOL_SIZE.set(stats.get("size", 0))
    DB_POOL_OVERFLOW.set(stats.get("overflow", 0))


def set_balance_gauges(
    *, reserved_balance_sum: int, available_balance_sum: int, accounts_total: int
) -> None:
    RESERVED_BALANCE_SUM.set(reserved_balance_sum)
    AVAILABLE_BALANCE_SUM.set(available_balance_sum)
    ACCOUNTS_TOTAL.set(accounts_total)


# ── Reading helpers (used by the summary endpoint and the tests) ──────────────


def render() -> bytes:
    """The Prometheus exposition payload."""
    return generate_latest(REGISTRY)


def exposed_metrics() -> list[str]:
    """Every metric family name exposed at ``/metrics`` (sorted).

    Used by the summary's coverage block and its test: if a metric is added
    without a corresponding field in the JSON view, coverage stops being 100%
    and the test fails.
    """
    return sorted(family.name for family in REGISTRY.collect())


def metric_value(metric, **labels: str) -> float:
    """Sum the samples of ``metric`` whose labels include ``labels``."""
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


def counter_table(metric) -> list[dict[str, object]]:
    """Flatten a labelled counter/gauge into ``[{**labels, "value": n}]`` rows."""
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


def table_to_map(metric, key: str) -> dict[str, int]:
    """Collapse a counter into ``{label_value: sum}`` for one label."""
    out: dict[str, int] = {}
    for row in counter_table(metric):
        label = str(row.get(key, "unknown"))
        out[label] = out.get(label, 0) + int(row["value"])
    return out


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


def percentile(buckets: dict[float, float], quantile: float) -> float | None:
    """Linear-interpolated percentile from cumulative histogram buckets."""
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


def histogram_stats(metric, **match: str) -> dict[str, float | None]:
    count, total = _count_and_sum(metric, **match)
    buckets = _buckets(metric, **match)
    return {
        "count": count,
        "sum_seconds": round(total, 6),
        "mean_seconds": round(total / count, 6) if count else None,
        "p50_seconds": percentile(buckets, 0.50),
        "p95_seconds": percentile(buckets, 0.95),
        "p99_seconds": percentile(buckets, 0.99),
    }


# ── Pre-shaped views used by the JSON summary ─────────────────────────────────


def http_summary() -> dict[str, object]:
    by_class = {"2xx": 0.0, "3xx": 0.0, "4xx": 0.0, "5xx": 0.0, "other": 0.0}
    per_route: dict[tuple[str, str], dict[str, float]] = {}
    failures = 0.0
    for row in counter_table(HTTP_REQUESTS):
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
        stats = histogram_stats(HTTP_DURATION, method=method, route=route)
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
    overall = histogram_stats(HTTP_DURATION)
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


def events_summary() -> dict[str, object]:
    published: dict[str, dict[str, float]] = {}
    for row in counter_table(EVENT_PUBLISH):
        routing_key = str(row.get("routing_key", "unknown"))
        result = str(row.get("result", "unknown"))
        bucket = published.setdefault(routing_key, {"ok": 0.0, "failed": 0.0})
        bucket[result] = bucket.get(result, 0.0) + float(row["value"])
    failures = sum(bucket.get("failed", 0.0) for bucket in published.values())
    stats = histogram_stats(EVENT_PUBLISH_DURATION)
    return {
        "published": {
            key: {result: int(value) for result, value in counts.items()}
            for key, counts in published.items()
        },
        "failed_total": int(failures),
        "publish_latency_seconds": {"mean": stats["mean_seconds"], "p95": stats["p95_seconds"]},
    }


def consumer_summary(queues: tuple[str, ...]) -> dict[str, object]:
    rows = []
    for queue in queues:
        last = metric_value(CONSUMER_LAST_MESSAGE, queue=queue)
        messages: dict[str, int] = {}
        for row in counter_table(CONSUMER_MESSAGES):
            if row.get("queue") != queue:
                continue
            result = str(row.get("result", "unknown"))
            messages[result] = messages.get(result, 0) + int(row["value"])
        requeues: dict[str, int] = {}
        for row in counter_table(CONSUMER_REQUEUES):
            if row.get("queue") != queue:
                continue
            reason = str(row.get("reason", "unknown"))
            requeues[reason] = requeues.get(reason, 0) + int(row["value"])
        rows.append(
            {
                "queue": queue,
                "connected": bool(metric_value(CONSUMER_CONNECTED, queue=queue)),
                "last_message_age_seconds": round(time.time() - last, 3) if last else None,
                "messages": messages,
                "requeues": requeues,
            }
        )
    return {"queues": rows}

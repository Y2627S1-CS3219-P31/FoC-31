# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Credit-service metrics: the shared layer plus the credit business counters.

The generic pieces (HTTP metrics, registry, helpers, ``/metrics`` and
``/health/ready`` routes) live in :mod:`foc_shared.observability`; this module
only declares the credit-specific families and keeps the names the rest of the
service (and its tests) already use.
"""

from __future__ import annotations

import time

from app.config import settings
from foc_shared.observability import Observability

OBS = Observability("credit-service", prefix="credit")

REGISTRY = OBS.registry
STARTED_AT = OBS.started_at

# HTTP families (shared definitions, re-exported under the old names).
HTTP_REQUESTS = OBS.http_requests
HTTP_DURATION = OBS.http_duration
HTTP_ERRORS = OBS.http_errors

# ── Business operations ───────────────────────────────────────────────────────

RESERVATION_OPS = OBS.counter(
    "credit_reservation_ops_total", "Reserve attempts by outcome.", ["outcome"]
)

AMENDMENT_OPS = OBS.counter(
    "credit_amendment_ops_total", "Reservation amendments by outcome.", ["outcome"]
)

TRANSFER_OPS = OBS.counter(
    "credit_transfer_ops_total", "Settlements to a courier by outcome.", ["outcome"]
)

RELEASE_OPS = OBS.counter(
    "credit_release_ops_total", "Reservation releases by outcome.", ["outcome"]
)

DUPLICATE_SUPPRESSED = OBS.counter(
    "credit_duplicate_suppressed_total",
    "Operations that would have applied twice but were suppressed as duplicates.",
    ["op"],
)

SAGA_TASKS = OBS.counter(
    "credit_saga_tasks_total",
    "Order Service task outcomes (release / amend / transfer).",
    ["kind", "outcome"],
)

SAGA_RETRIES_EXHAUSTED = OBS.counter(
    "credit_saga_retries_exhausted_total",
    "Order Service tasks that used up the retry budget before answering.",
    ["kind"],
)

# ── Event integration (RabbitMQ) ──────────────────────────────────────────────

EVENT_PUBLISH = OBS.counter(
    "credit_event_publish_total",
    "Events published to foc.credit.events by routing key and result.",
    ["routing_key", "result"],
)

EVENT_PUBLISH_DURATION = OBS.histogram(
    "credit_event_publish_duration_seconds",
    "Time spent publishing one event (connection setup included).",
    ["routing_key"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0, 3.0, 5.0),
)

CONSUMER_MESSAGES = OBS.counter(
    "credit_consumer_messages_total",
    "Consumed messages by queue and handling result.",
    ["queue", "result"],
)

CONSUMER_REQUEUES = OBS.counter(
    "credit_consumer_requeues_total",
    "Consumer retry/requeue decisions by queue and reason.",
    ["queue", "reason"],
)

CONSUMER_LAST_MESSAGE = OBS.gauge(
    "credit_consumer_last_message_unixtime",
    "Unix time of the last message handled per queue (staleness signal).",
    ["queue"],
)

CONSUMER_CONNECTED = OBS.gauge(
    "credit_consumer_connected",
    "1 when the consumer holds a live connection for the queue.",
    ["queue"],
)

# ── Resources ─────────────────────────────────────────────────────────────────

DB_POOL_IN_USE = OBS.gauge("credit_db_pool_in_use", "Database connections currently checked out.")
DB_POOL_SIZE = OBS.gauge("credit_db_pool_size", "Configured database pool size.")
DB_POOL_OVERFLOW = OBS.gauge(
    "credit_db_pool_overflow", "Database connections open beyond the pool size."
)
RESERVED_BALANCE_SUM = OBS.gauge(
    "credit_reserved_balance_sum",
    "Credits currently held in reservations across all accounts.",
)
AVAILABLE_BALANCE_SUM = OBS.gauge(
    "credit_available_balance_sum", "Credits currently spendable across all accounts."
)
ACCOUNTS_TOTAL = OBS.gauge("credit_accounts_total", "Credit accounts provisioned.")


# ── Recording helpers ─────────────────────────────────────────────────────────

route_template = OBS.route_template
observe_http_request = OBS.observe_http_request
record_error_code = OBS.record_error_code
metric_value = OBS.value
counter_table = OBS.table
table_to_map = OBS.table_to_map
histogram_stats = OBS.histogram_stats
percentile = OBS.percentile
http_summary = OBS.http_summary
render = OBS.render
exposed_metrics = OBS.exposed_metrics


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


# ── Credit-specific views ─────────────────────────────────────────────────────


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


def configure_logging() -> None:
    """Credit-service logging configuration (JSON in containers)."""
    from foc_shared.observability import configure_logging as _configure

    _configure(level=settings.log_level, json_output=settings.log_json, logger_name="app")

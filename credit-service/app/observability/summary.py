# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Assembles the JSON view served by ``GET /credits/observability/summary``.

This is the "data display" API: a single JSON block that answers, at a glance,
*is the service healthy, what is slow, what is failing, and is the async path
alive*. It is derived from the same registry Prometheus scrapes, plus a live
database read for the balance aggregates, so the two can never disagree.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from app.config import settings
from app.db import pool_stats
from app.observability import health as broker_health
from app.observability import metrics
from app.services.credit_service import CreditService

# A queue whose last message is older than this is reported as stalled: the
# consumer can look perfectly "connected" while silently consuming nothing.
STALLED_AFTER_SECONDS = 300.0

# Every metric family exposed at /metrics -> the JSON field that carries it.
# Kept as data so `coverage()` can prove the display endpoint really covers the
# exposition, and so `tests/test_observability.py` fails if the two drift apart.
METRIC_COVERAGE: dict[str, str] = {
    "credit_http_requests": "http.total_requests",
    "credit_http_request_duration_seconds": "http.latency_seconds",
    "credit_http_errors": "errors_by_code",
    "credit_reservation_ops": "business.reservations",
    "credit_amendment_ops": "business.amendments",
    "credit_transfer_ops": "business.transfers",
    "credit_release_ops": "business.releases",
    "credit_duplicate_suppressed": "business.duplicate_suppressed",
    "credit_saga_tasks": "saga.tasks",
    "credit_saga_retries_exhausted": "saga.retries_exhausted",
    "credit_event_publish": "events.published",
    "credit_event_publish_duration_seconds": "events.publish_latency_seconds",
    "credit_consumer_messages": "consumer.queues",
    "credit_consumer_requeues": "consumer.queues",
    "credit_consumer_last_message_unixtime": "consumer.queues",
    "credit_consumer_connected": "consumer.queues",
    "credit_db_pool_in_use": "database.pool.in_use",
    "credit_db_pool_size": "database.pool.size",
    "credit_db_pool_overflow": "database.pool.overflow",
    "credit_reserved_balance_sum": "database.reserved_balance_sum",
    "credit_available_balance_sum": "database.available_balance_sum",
    "credit_accounts_total": "database.accounts_total",
}

_MISSING = object()


def _resolve(payload: object, dotted: str) -> object:
    """Walk ``a.b.c`` through dicts, descending into the first list element."""
    node: object = payload
    for part in dotted.split("."):
        if isinstance(node, list):
            node = node[0] if node else _MISSING
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


def coverage(payload: dict[str, object]) -> dict[str, object]:
    """Report which exposed metrics the JSON view carries (the display contract)."""
    exposed = metrics.exposed_metrics()
    by_metric: dict[str, str | None] = {}
    missing: list[str] = []
    for family in exposed:
        path = METRIC_COVERAGE.get(family)
        if path is None or _resolve(payload, path) is _MISSING:
            by_metric[family] = path
            missing.append(family)
        else:
            by_metric[family] = path
    return {
        "metrics_exposed": len(exposed),
        "metrics_covered": len(exposed) - len(missing),
        "missing": missing,
        "field_by_metric": by_metric,
    }


async def build_summary(service: CreditService) -> dict[str, object]:
    totals = await service.balance_totals()
    metrics.set_balance_gauges(**totals)
    metrics.set_pool_gauges(pool_stats())

    http = metrics.http_summary()
    availability = http["availability"]
    slo = settings.availability_slo
    error_budget = None
    if availability is not None:
        allowed = max(1.0 - slo, 1e-9)
        error_budget = round(1.0 - (1.0 - availability) / allowed, 6)

    queues = tuple(settings.consumer_queues)
    consumer = metrics.consumer_summary(queues)
    stalled = [
        row["queue"]
        for row in consumer["queues"]
        if row["last_message_age_seconds"] is not None
        and row["last_message_age_seconds"] > STALLED_AFTER_SECONDS
    ]
    broker = broker_health.broker_state()

    return _with_coverage(
        {
            "service": settings.service_name,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "uptime_seconds": round(time.time() - metrics.STARTED_AT, 3),
            "window": "since process start",
            "http": http,
            "errors_by_code": metrics.table_to_map(metrics.HTTP_ERRORS, "code"),
            "business": {
                "reservations": metrics.table_to_map(metrics.RESERVATION_OPS, "outcome"),
                "amendments": metrics.table_to_map(metrics.AMENDMENT_OPS, "outcome"),
                "transfers": metrics.table_to_map(metrics.TRANSFER_OPS, "outcome"),
                "releases": metrics.table_to_map(metrics.RELEASE_OPS, "outcome"),
                "duplicate_suppressed": metrics.table_to_map(metrics.DUPLICATE_SUPPRESSED, "op"),
            },
            "saga": {
                "tasks": {
                    f"{row['kind']}:{row['outcome']}": int(row["value"])
                    for row in metrics.counter_table(metrics.SAGA_TASKS)
                },
                "retries_exhausted": metrics.table_to_map(metrics.SAGA_RETRIES_EXHAUSTED, "kind"),
            },
            "events": metrics.events_summary(),
            "consumer": consumer,
            "database": {
                "accounts_total": totals["accounts_total"],
                "available_balance_sum": totals["available_balance_sum"],
                "reserved_balance_sum": totals["reserved_balance_sum"],
                "pool": pool_stats(),
            },
            "slo": {
                "availability_target": slo,
                "availability_actual": availability,
                "server_error_rate": http["server_error_rate"],
                "error_budget_remaining_fraction": error_budget,
            },
            "health": {
                "status": "ok" if not stalled and not broker["error"] else "degraded",
                "broker_connected": bool(broker["connected"]),
                "broker_error": broker["error"],
                "stalled_queues": stalled,
                "stalled_after_seconds": STALLED_AFTER_SECONDS,
            },
        }
    )


def _with_coverage(payload: dict[str, object]) -> dict[str, object]:
    """Attach the metric-coverage block (proves the view covers /metrics)."""
    payload["coverage"] = coverage(payload)
    return payload

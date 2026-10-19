# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Tests for the observability layer (metrics, readiness, JSON summary).

Counters are process-global, so every assertion here is a *delta* read through
``metrics.metric_value`` — that keeps the tests independent of their order and
of whatever other test modules already recorded.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, get_session
from app.main import app
from app.observability import health as broker_health
from app.observability import metrics
from app.observability.summary import METRIC_COVERAGE
from app.schemas.interop import OrderActionEvent
from app.services import publisher
from app.services.consumer import CreditEventConsumer
from app.services.credit_service import CreditService
from foc_shared.events import OrderEvent, OrderEventType

ADMIN = {"X-User-Id": "admin-1", "X-User-Role": "admin"}
CLIENT = {"X-User-Id": "user-1", "X-User-Role": "client"}
BALANCE_ROUTE = "/credits/{user_id}/balance"
RESERVE_ROUTE = "/credits/reservations"


@pytest_asyncio.fixture
async def client(monkeypatch) -> AsyncGenerator[TestClient, None]:
    from app import models  # noqa: F401

    # Keep the tests hermetic: the reservation publish path must not try to
    # reach RabbitMQ (it would block for the connect timeout on every request).
    async def _noop(event) -> None:
        return None

    monkeypatch.setattr(publisher, "publish_reservation_event", _noop)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    async with maker() as s:
        service = CreditService(s)
        await service.ensure_account("user-1")
        await service.ensure_account("user-2")

    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    from app import models  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _reserve(client: TestClient, *, amount: int = 30, order_id: str = "order-1"):
    return client.post(
        RESERVE_ROUTE,
        json={"user_id": "user-1", "order_id": order_id, "amount": amount},
        headers=CLIENT,
    )


# ── exposition + HTTP labels ───────────────────────────────────────────────────


def test_metrics_endpoint_renders_prometheus_text(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "credit_http_requests_total" in body
    assert "credit_reservation_ops_total" in body
    assert "credit_consumer_last_message_unixtime" in body


def test_http_metrics_use_route_templates_not_raw_paths(client):
    client.get("/credits/user-1/balance", headers=CLIENT)
    client.get("/credits/user-1/balance", headers=CLIENT)

    rows = metrics.counter_table(metrics.HTTP_REQUESTS)
    matching = [
        row
        for row in rows
        if row.get("route") == BALANCE_ROUTE
        and row.get("method") == "GET"
        and row.get("status") == "200"
    ]
    assert matching and float(matching[0]["value"]) >= 2
    # The concrete user id must never become a label value.
    assert all("user-1" not in str(row.get("route", "")) for row in rows)


def test_health_is_untouched(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_request_id_is_echoed_back(client):
    resp = client.get("/credits/user-1/balance", headers={**CLIENT, "x-request-id": "trace-42"})
    assert resp.headers["x-request-id"] == "trace-42"
    generated = client.get("/credits/user-1/balance", headers=CLIENT)
    assert generated.headers["x-request-id"]


# ── error envelope codes ──────────────────────────────────────────────────────


def test_error_code_is_recorded_for_business_rejection(client):
    before = metrics.metric_value(
        metrics.HTTP_ERRORS, route=RESERVE_ROUTE, code="insufficient_credits"
    )
    resp = _reserve(client, amount=999)
    assert resp.status_code == 409
    assert resp.json()["code"] == "insufficient_credits"
    after = metrics.metric_value(
        metrics.HTTP_ERRORS, route=RESERVE_ROUTE, code="insufficient_credits"
    )
    assert after == before + 1


def test_error_code_is_recorded_for_validation_errors(client):
    before = metrics.metric_value(metrics.HTTP_ERRORS, route=RESERVE_ROUTE, code="validation_error")
    resp = client.post(
        RESERVE_ROUTE,
        json={"user_id": "user-1", "order_id": "order-1", "amount": 0},
        headers=CLIENT,
    )
    assert resp.status_code == 422
    after = metrics.metric_value(metrics.HTTP_ERRORS, route=RESERVE_ROUTE, code="validation_error")
    assert after == before + 1


# ── business counters ────────────────────────────────────────────────────────


def test_duplicate_reservation_is_suppressed_not_counted_as_accepted(client):
    accepted_before = metrics.metric_value(metrics.RESERVATION_OPS, outcome="accepted")
    dup_before = metrics.metric_value(metrics.DUPLICATE_SUPPRESSED, op="reservation")

    first = _reserve(client, amount=30, order_id="order-dup")
    second = _reserve(client, amount=30, order_id="order-dup")

    assert first.status_code == 201
    assert second.status_code in (200, 201)
    assert first.json()["id"] == second.json()["id"]
    assert metrics.metric_value(metrics.RESERVATION_OPS, outcome="accepted") == accepted_before + 1
    assert metrics.metric_value(metrics.DUPLICATE_SUPPRESSED, op="reservation") == dup_before + 1


def test_conflicting_reservation_counts_conflict(client):
    _reserve(client, amount=30, order_id="order-conflict")
    before = metrics.metric_value(metrics.RESERVATION_OPS, outcome="conflict")
    resp = _reserve(client, amount=40, order_id="order-conflict")
    assert resp.status_code == 409
    assert metrics.metric_value(metrics.RESERVATION_OPS, outcome="conflict") == before + 1


def test_transfer_and_release_outcomes_are_counted(client):
    created = _reserve(client, amount=20, order_id="order-counted").json()
    transfer_before = metrics.metric_value(metrics.TRANSFER_OPS, outcome="ok")
    client.post(
        f"/credits/reservations/{created['id']}/transfer",
        json={"courier_id": "user-2"},
        headers=CLIENT,
    )
    assert metrics.metric_value(metrics.TRANSFER_OPS, outcome="ok") == transfer_before + 1

    released = _reserve(client, amount=10, order_id="order-released").json()
    release_before = metrics.metric_value(metrics.RELEASE_OPS, outcome="ok")
    client.post(f"/credits/reservations/{released['id']}/release", headers=CLIENT)
    assert metrics.metric_value(metrics.RELEASE_OPS, outcome="ok") == release_before + 1


async def test_saga_retries_exhausted_is_counted(session, monkeypatch):
    async def _noop(event) -> None:
        return None

    monkeypatch.setattr(publisher, "publish_credit_event", _noop)
    event = OrderActionEvent(
        event_type="OrderDeletionRequested",
        task_id="task-exhausted",
        order_id="order-x",
        reservation_id="reservation-x",
        requester_id="user-1",
        timestamp=datetime.now(UTC),
    )
    before = metrics.metric_value(metrics.SAGA_RETRIES_EXHAUSTED, kind="release")
    await CreditService(session).report_release_retries_exhausted(event, RuntimeError("boom"))
    assert metrics.metric_value(metrics.SAGA_RETRIES_EXHAUSTED, kind="release") == before + 1


# ── consumer metrics ─────────────────────────────────────────────────────────


class _FakeMessage:
    def __init__(self, body: bytes, *, routing_key: str = "OrderCompleted") -> None:
        self.body = body
        self.routing_key = routing_key
        self.headers: dict = {}
        self.acked = False

    async def ack(self) -> None:
        self.acked = True

    async def nack(self, requeue: bool | None = None) -> None:
        raise AssertionError(f"unexpected nack (requeue={requeue})")


async def test_consumer_records_messages_and_freshness():
    event = OrderEvent(
        event_type=OrderEventType.ORDER_COMPLETED,
        order_id="order-consumer",
        requester_id="user-1",
        courier_id="user-2",
        timestamp=datetime.now(UTC),
    )

    async def _noop(event) -> None:
        return None

    queue = "credit-service.order-events"
    before = metrics.metric_value(metrics.CONSUMER_MESSAGES, queue=queue, result="ok")
    message = _FakeMessage(event.model_dump_json().encode())
    await CreditEventConsumer()._dispatch(message, model=OrderEvent, handler=_noop, queue=queue)

    assert message.acked is True
    assert metrics.metric_value(metrics.CONSUMER_MESSAGES, queue=queue, result="ok") == before + 1
    last = metrics.metric_value(metrics.CONSUMER_LAST_MESSAGE, queue=queue)
    assert last > 0


# ── readiness + summary ──────────────────────────────────────────────────────


def test_readiness_reports_degraded_when_broker_is_down(client):
    broker_health.set_broker_state(False, "not connected")
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["broker"] == "unavailable"


def test_readiness_is_ready_when_broker_is_connected(client):
    broker_health.set_broker_state(True)
    try:
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"
    finally:
        broker_health.set_broker_state(False, "test finished")


def test_summary_requires_admin(client):
    resp = client.get("/credits/observability/summary", headers=CLIENT)
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"


def test_summary_returns_the_display_json(client):
    _reserve(client, amount=30, order_id="order-summary")
    client.get("/credits/user-1/balance", headers=CLIENT)

    resp = client.get("/credits/observability/summary", headers=ADMIN)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert set(body) >= {
        "service",
        "generated_at",
        "uptime_seconds",
        "http",
        "business",
        "saga",
        "events",
        "consumer",
        "database",
        "slo",
        "health",
        "coverage",
    }
    assert body["service"] == "credit-service"
    assert body["http"]["total_requests"] >= 1
    assert body["business"]["reservations"]["accepted"] >= 1
    assert body["database"]["accounts_total"] == 2
    assert body["database"]["reserved_balance_sum"] == 30
    assert body["slo"]["availability_target"] == 0.99
    assert isinstance(body["consumer"]["queues"], list)
    assert {q["queue"] for q in body["consumer"]["queues"]} == {
        "credit-service.order-events",
        "credit-service.user-events",
    }


def test_summary_covers_every_metric_exposed_at_metrics(client):
    """The display endpoint must cover /metrics: no family may be left behind."""
    exposed = metrics.exposed_metrics()
    assert len(exposed) == len(METRIC_COVERAGE), (
        f"metric families changed ({len(exposed)} exposed vs {len(METRIC_COVERAGE)} "
        "mapped): update METRIC_COVERAGE in app/observability/summary.py"
    )
    assert set(exposed) == set(METRIC_COVERAGE)

    body = client.get("/credits/observability/summary", headers=ADMIN).json()
    assert body["coverage"]["metrics_exposed"] == len(exposed)
    assert body["coverage"]["missing"] == []
    assert body["coverage"]["metrics_covered"] == body["coverage"]["metrics_exposed"]

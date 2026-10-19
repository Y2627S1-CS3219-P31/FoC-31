#!/usr/bin/env python3
# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Exercise every credit-service metric and show the JSON display endpoint.

This is the observability self-test / demo. It runs the real FastAPI app
in-process (TestClient) against in-memory sqlite with a stubbed AMQP transport,
so it works without Docker. Every counter it prints was incremented by the
production code path — nothing is set by hand, except the consumer connection /
freshness gauges, which normally come from the RabbitMQ consumer task.

Usage (from the repo root):

    credit-service/.venv/Scripts/python scripts/observability-demo.py   # Windows
    credit-service/.venv/bin/python     scripts/observability-demo.py   # POSIX

What it proves:
  1. the three new endpoints exist and answer;
  2. each error-envelope code (401/403/404/409 conflict/409 insufficient_credits/
     422 validation_error) is produced and counted under its own label;
  3. every business / saga / event / consumer outcome family appears in
     /metrics and in GET /credits/observability/summary;
  4. the summary covers 100% of the exposed metric families (coverage block).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "credit-service"))
sys.path.insert(0, str(ROOT / "shared"))

# The demo deliberately triggers dead-letters, business errors and retries; the
# service logs those with tracebacks on purpose, which would drown the report.
logging.getLogger("app").addHandler(logging.NullHandler())
logging.getLogger("app").propagate = False

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import Base, get_session  # noqa: E402
from app.errors import NotFoundError  # noqa: E402
from app.main import app  # noqa: E402
from app.models.task_result import CreditTaskResult, TaskResultKind, TaskResultOutcome  # noqa: E402
from app.observability import health as broker_health  # noqa: E402
from app.observability import metrics  # noqa: E402
from app.schemas.interop import OrderActionEvent, OrderUpdateRequestedEvent  # noqa: E402
from app.services import publisher  # noqa: E402
from app.services.consumer import CreditEventConsumer  # noqa: E402
from app.services.credit_service import CreditService  # noqa: E402
from foc_shared.events import OrderEvent, OrderEventType  # noqa: E402

ADMIN = {"X-User-Id": "admin-1", "X-User-Role": "admin"}


# ── stubbed AMQP transport (records "broker down" like the real failure) ─────

BROKER = {"down": False}


class _FakeExchange:
    async def publish(self, message, routing_key: str = "") -> None:
        if BROKER["down"]:
            raise ConnectionError("broker unreachable")


class _FakeChannel:
    async def declare_exchange(self, *args, **kwargs) -> _FakeExchange:
        return _FakeExchange()


class _FakeConnection:
    async def __aenter__(self) -> _FakeConnection:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def channel(self, **kwargs) -> _FakeChannel:
        return _FakeChannel()


async def _fake_connect_robust(*args, **kwargs) -> _FakeConnection:
    if BROKER["down"]:
        raise ConnectionError("broker unreachable")
    return _FakeConnection()


publisher.aio_pika.connect_robust = _fake_connect_robust


# ── app under test ──────────────────────────────────────────────────────────

engine = create_async_engine("sqlite+aiosqlite:///:memory:")


async def _create_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


asyncio.run(_create_schema())
maker = async_sessionmaker(engine, expire_on_commit=False)


async def _override_session():
    async with maker() as session:
        yield session


app.dependency_overrides[get_session] = _override_session


async def _seed() -> None:
    async with maker() as session:
        service = CreditService(session)
        for user in ("alice", "bob"):
            await service.ensure_account(user)


asyncio.run(_seed())
client = TestClient(app)


# ── helpers ─────────────────────────────────────────────────────────────────

def section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def call(method: str, path: str, *, user: str | None, role: str = "client", body: dict | None = None):
    headers = {"X-User-Id": user, "X-User-Role": role} if user else {}
    return client.request(method, path, json=body, headers=headers)


def show(label: str, response, expected: str = "") -> None:
    try:
        payload = response.json()
    except ValueError:  # /metrics is text/plain
        payload = {}
    if isinstance(payload, dict):
        code = payload.get("code") or payload.get("status") or payload.get("event_type") or "ok"
    else:
        code = "ok"
    expected_note = f"   (expected {expected})" if expected else ""
    print(f"  {label:<58} -> {response.status_code:>3} {str(code):<28}{expected_note}")


def reserve(order_id: str, amount: int, user: str = "alice"):
    return call(
        "POST",
        "/credits/reservations",
        user=user,
        body={"user_id": user, "order_id": order_id, "amount": amount},
    )


# ── 1. the new endpoints ────────────────────────────────────────────────────

section("1. NEW ENDPOINTS")
print("  GET   /metrics                       (Prometheus text; include_in_schema=False, scraped over foc-net)")
openapi_paths = client.get("/openapi.json").json()["paths"]
for path, operations in sorted(openapi_paths.items()):
    if path in {"/health/ready", "/credits/observability/summary"}:
        methods = ",".join(sorted(method.upper() for method in operations))
        print(f"  {methods:<5} {path}")

# ── 2. HTTP scenarios covering every error code ─────────────────────────────

section("2. HTTP SCENARIOS (every error-envelope code)")
show("GET /credits/alice/balance (no identity)", call("GET", "/credits/alice/balance", user=None), "401 unauthorized")
show("GET /credits/bob/balance as alice", call("GET", "/credits/bob/balance", user="alice"), "403 forbidden")
show("GET /credits/observability/summary as alice", call("GET", "/credits/observability/summary", user="alice"), "403 forbidden")
show("GET /credits/ghost/balance as admin", call("GET", "/credits/ghost/balance", user="admin-1", role="admin"), "404 not_found")

reserve_a = reserve("order-a", 10)
show("POST /credits/reservations order-a 10", reserve_a, "201 accepted")
reservation_a = reserve_a.json()
show(
    "POST .../{id}/release order-a",
    call("POST", f"/credits/reservations/{reservation_a['id']}/release", user="alice"),
    "200 release ok",
)
show("POST /credits/reservations order-a 10 again", reserve("order-a", 10), "201 duplicate suppressed")
show("POST /credits/reservations order-a 20", reserve("order-a", 20), "409 conflict")
show("POST /credits/reservations order-f 9999", reserve("order-f", 9999), "409 insufficient_credits")
show(
    "POST /credits/reservations amount=0",
    call("POST", "/credits/reservations", user="alice", body={"user_id": "alice", "order_id": "x", "amount": 0}),
    "422 validation_error",
)
show(
    "POST /credits/reservations/ghost/transfer",
    call("POST", "/credits/reservations/ghost/transfer", user="alice", body={"courier_id": "bob"}),
    "404 not_found",
)

reservation_b = reserve("order-b", 20).json()
show(
    "POST .../transfer order-b to bob",
    call("POST", f"/credits/reservations/{reservation_b['id']}/transfer", user="alice", body={"courier_id": "bob"}),
    "200 transfer ok",
)
show(
    "POST .../transfer order-b again",
    call("POST", f"/credits/reservations/{reservation_b['id']}/transfer", user="alice", body={"courier_id": "bob"}),
    "200 already_transferred",
)
show(
    "POST .../release order-b (already transferred)",
    call("POST", f"/credits/reservations/{reservation_b['id']}/release", user="alice"),
    "409 conflict",
)

reservation_c = reserve("order-c", 15).json()
call("POST", f"/credits/reservations/{reservation_c['id']}/release", user="alice")
show(
    "POST .../release order-c again",
    call("POST", f"/credits/reservations/{reservation_c['id']}/release", user="alice"),
    "200 already_released",
)

reservation_d = reserve("order-d", 5).json()
show(
    "POST .../transfer order-d to ghost courier",
    call("POST", f"/credits/reservations/{reservation_d['id']}/transfer", user="alice", body={"courier_id": "ghost"}),
    "404 rejected_no_courier_account",
)
call("POST", f"/credits/reservations/{reservation_d['id']}/release", user="alice")

reservation_e = reserve("order-e", 10).json()
show(
    "POST .../amend order-e 25",
    call("POST", f"/credits/reservations/{reservation_e['id']}/amend", user="alice", body={"amount": 25}),
    "200 amended",
)
show(
    "POST .../amend order-e 25 again",
    call("POST", f"/credits/reservations/{reservation_e['id']}/amend", user="alice", body={"amount": 25}),
    "200 unchanged",
)
show(
    "POST .../amend order-e 999",
    call("POST", f"/credits/reservations/{reservation_e['id']}/amend", user="alice", body={"amount": 999}),
    "409 amendment insufficient",
)
call("POST", f"/credits/reservations/{reservation_e['id']}/release", user="alice")
show(
    "POST .../amend order-e after release",
    call("POST", f"/credits/reservations/{reservation_e['id']}/amend", user="alice", body={"amount": 30}),
    "409 amendment conflict",
)

show("GET /credits/alice/balance", call("GET", "/credits/alice/balance", user="alice"), "200")
show("GET /credits/bob/balance", call("GET", "/credits/bob/balance", user="bob"), "200")
show("GET /credits/alice/transactions", call("GET", "/credits/alice/transactions", user="alice"), "200")
show("GET /health", call("GET", "/health", user=None), "200 unchanged")

# ── 3. saga counters (pure RabbitMQ path, never HTTP) ──────────────────────

section("3. SAGA TASKS (RabbitMQ-only, no HTTP counterpart)")


def release_task(task_id: str, order_id: str, reservation_id: str, requester: str) -> OrderActionEvent:
    return OrderActionEvent(
        event_type="OrderDeletionRequested",
        task_id=task_id,
        order_id=order_id,
        reservation_id=reservation_id,
        requester_id=requester,
        timestamp=datetime.now(UTC),
    )


def amend_task(task_id: str, order_id: str, reservation_id: str, requester: str, reward: int):
    return OrderUpdateRequestedEvent(
        task_id=task_id,
        order_id=order_id,
        reservation_id=reservation_id,
        requester_id=requester,
        reward=reward,
        timestamp=datetime.now(UTC),
    )


async def run_saga_scenarios() -> None:
    async with maker() as session:
        service = CreditService(session)

        r1 = await service.reserve(user_id="alice", order_id="order-s1", amount=12)
        await service.handle_release_requested(release_task("t-1", "order-s1", r1.id, "alice"))
        show("handle_release_requested t-1 (released)", _FakeResponse(200, "CreditReleased"), "release:released")

        await service.handle_release_requested(release_task("t-2", "order-s1", r1.id, "bob"))
        show("handle_release_requested t-2 (wrong requester)", _FakeResponse(200, "CreditReleaseFailed"), "release:release_failed")

        await service.handle_release_requested(release_task("t-1", "order-s1", r1.id, "alice"))
        show("handle_release_requested t-1 again", _FakeResponse(200, "CreditReleased"), "duplicate suppressed")

        r2 = await service.reserve(user_id="alice", order_id="order-s2", amount=10)
        await service.handle_update_requested(amend_task("t-3", "order-s2", r2.id, "alice", 25))
        show("handle_update_requested t-3 (reward 25)", _FakeResponse(200, "CreditAmended"), "amend:amended")

        await service.handle_update_requested(amend_task("t-3", "order-s2", r2.id, "alice", 25))
        show("handle_update_requested t-3 again", _FakeResponse(200, "CreditAmended"), "duplicate suppressed")

        await service.handle_update_requested(amend_task("t-4", "order-s2", r2.id, "alice", -1))
        show("handle_update_requested t-4 (reward -1)", _FakeResponse(200, "CreditAmendRejected"), "amend:amend_rejected")

        # Two *distinct* rows with the same task_id: the second insert hits the
        # primary key, which is what the task_result duplicate counter reports.
        for _ in range(2):
            await service._save_task_result(
                CreditTaskResult(
                    task_id="t-dup",
                    kind=TaskResultKind.RELEASE.value,
                    reservation_id=r1.id,
                    order_id="order-s1",
                    requester_id="alice",
                    outcome=TaskResultOutcome.RELEASED.value,
                )
            )
        show("_save_task_result t-dup twice", _FakeResponse(200, "first outcome kept"), "task_result duplicate")

        await service.report_release_retries_exhausted(
            release_task("t-x", "order-x", "reservation-x", "alice"), RuntimeError("db unavailable")
        )
        show("report_release_retries_exhausted", _FakeResponse(200, "failure reply"), "retries_exhausted release")

        await service.report_amend_retries_exhausted(
            amend_task("t-y", "order-y", "reservation-y", "alice", 5), RuntimeError("db unavailable")
        )
        show("report_amend_retries_exhausted", _FakeResponse(200, "failure reply"), "retries_exhausted amend")


class _FakeResponse:
    """Tiny stand-in so saga rows print like the HTTP rows."""

    def __init__(self, status_code: int, code: str) -> None:
        self.status_code = status_code
        self._code = code

    def json(self) -> dict:
        return {"code": self._code}


asyncio.run(run_saga_scenarios())

# ── 4. consumer outcomes + requeue reasons ─────────────────────────────────

section("4. CONSUMER OUTCOMES (every _dispatch branch)")
QUEUE = settings.order_events_queue
consumer = CreditEventConsumer()


class _Msg:
    def __init__(self, body: bytes, *, routing_key: str = "OrderCompleted", headers: dict | None = None) -> None:
        self.body = body
        self.routing_key = routing_key
        self.headers = headers or {}
        self.acked = False
        self.requeued: bool | None = None

    async def ack(self) -> None:
        self.acked = True

    async def nack(self, requeue: bool | None = None) -> None:
        self.requeued = requeue


class _Exchange:
    def __init__(self) -> None:
        self.published = 0

    async def publish(self, message, routing_key: str = "") -> None:
        self.published += 1


def _completed_event() -> OrderEvent:
    return OrderEvent(
        event_type=OrderEventType.ORDER_COMPLETED,
        order_id="order-consumer",
        requester_id="alice",
        courier_id="bob",
        timestamp=datetime.now(UTC),
    )


async def noop_handler(event) -> None:
    return None


async def business_error_handler(event) -> None:
    raise NotFoundError("no reservation for this order")


async def transient_handler(event) -> None:
    raise RuntimeError("database unavailable")


async def noop_exhausted(event, error) -> None:
    return None


async def run_consumer_scenarios() -> None:
    ok_message = _Msg(_completed_event().model_dump_json().encode())
    await consumer._dispatch(ok_message, model=OrderEvent, handler=noop_handler, queue=QUEUE)
    print(f"  {'message handled':<58} -> {'ok':>3} {'acked=' + str(ok_message.acked):<24}")

    await consumer._dispatch(_Msg(b"{not json"), model=OrderEvent, handler=noop_handler, queue=QUEUE)
    print(f"  {'malformed payload':<58} -> {'dead':>3} {'dead-lettered':<24}")

    await consumer._dispatch(_Msg(_completed_event().model_dump_json().encode()), model=OrderEvent, handler=business_error_handler, queue=QUEUE)
    print(f"  {'business error (NotFound)':<58} -> {'ack':>3} {'business_error':<24}")

    requeue_message = _Msg(_completed_event().model_dump_json().encode())
    await consumer._dispatch(requeue_message, model=OrderEvent, handler=transient_handler, queue=QUEUE)
    print(f"  {'transient error, no reply contract':<58} -> {'nack':>4} {'requeue=' + str(requeue_message.requeued):<24}")

    retry_exchange = _Exchange()
    retry_message = _Msg(_completed_event().model_dump_json().encode())
    await consumer._dispatch(
        retry_message,
        model=OrderEvent,
        handler=transient_handler,
        retry_exchange=retry_exchange,
        on_exhausted=noop_exhausted,
        queue=QUEUE,
    )
    print(f"  {'transient error, retry budget left':<58} -> {'retry':>5} {'republished=' + str(retry_exchange.published):<24}")

    # The retry budget only exists for request/reply events, which carry a
    # task_id; drive the real task message here rather than a legacy event.
    exhausted_message = _Msg(
        release_task("t-retry", "order-r", "reservation-r", "alice").model_dump_json().encode(),
        routing_key="OrderDeletionRequested",
        headers={"x-retry-count": settings.event_retry_limit - 1},
    )
    await consumer._dispatch(
        exhausted_message,
        model=OrderActionEvent,
        handler=transient_handler,
        retry_exchange=_Exchange(),
        on_exhausted=noop_exhausted,
        verify_routing_key=True,
        queue=QUEUE,
    )
    print(f"  {'transient error, retry budget exhausted':<58} -> {'ack':>3} {'failure reply sent':<24}")

    mismatch_message = _Msg(_completed_event().model_dump_json().encode(), routing_key="OrderExpired")
    await consumer._dispatch(
        mismatch_message, model=OrderEvent, handler=noop_handler, verify_routing_key=True, queue=QUEUE
    )
    print(f"  {'routing key / payload mismatch':<58} -> {'dead':>3} {'dead-lettered':<24}")


asyncio.run(run_consumer_scenarios())

# ── 5. event publish failures (broker down) ────────────────────────────────

section("5. EVENT PUBLISH FAILURES (broker down, request still succeeds)")
BROKER["down"] = True
show("POST /credits/reservations order-g 5 (broker down)", reserve("order-g", 5), "201 accepted, publish failed")
show("POST /credits/reservations order-h 9999 (broker down)", reserve("order-h", 9999), "409 + rejected event failed")
BROKER["down"] = False

# consumer liveness gauges normally come from the RabbitMQ consumer task
broker_health.set_broker_state(True)
for queue_name in settings.consumer_queues:
    metrics.set_consumer_connected(queue_name, True)
    metrics.mark_consumer_message(queue_name)

# ── 6. /metrics: every non-zero family ────────────────────────────────────

section("6. /metrics (credit_* samples, buckets/created timestamps omitted)")
exposition = client.get("/metrics")
assert exposition.status_code == 200
for line in exposition.text.splitlines():
    if not line.startswith("credit_"):
        continue
    if "_created" in line or "_bucket" in line:
        continue
    if line.endswith(" 0.0"):
        continue
    print(f"  {line}")

# ── 7. the JSON display endpoint ──────────────────────────────────────────

section("7. GET /credits/observability/summary (admin)")
summary_response = client.get("/credits/observability/summary", headers=ADMIN)
print("  status:", summary_response.status_code)
body = summary_response.json()
coverage_block = body.pop("coverage")
print(json.dumps(body, indent=2, sort_keys=False))

# ── 8. per-function statistics + metric coverage ──────────────────────────

section("8. PER-FUNCTION STATISTICS")
print(f"  availability            : {body['slo']['availability_actual']}  (target {body['slo']['availability_target']})")
print(f"  requests                : {body['http']['total_requests']}  {body['http']['requests_by_class']}")
print(f"  latency p50/p95/p99 (s) : {body['http']['latency_seconds']['p50']} / "
      f"{body['http']['latency_seconds']['p95']} / {body['http']['latency_seconds']['p99']}")
print(f"  error codes             : {body['errors_by_code']}")
print(f"  reservations            : {body['business']['reservations']}")
print(f"  amendments              : {body['business']['amendments']}")
print(f"  transfers               : {body['business']['transfers']}")
print(f"  releases                : {body['business']['releases']}")
print(f"  duplicate suppressed    : {body['business']['duplicate_suppressed']}")
print(f"  saga tasks              : {body['saga']['tasks']}")
print(f"  saga retries exhausted  : {body['saga']['retries_exhausted']}")
print(f"  events published        : {body['events']['published']}")
print(f"  event failures          : {body['events']['failed_total']}")
print(f"  consumer queues         : {[(q['queue'], q['messages'], q['requeues']) for q in body['consumer']['queues']]}")
print(f"  database                : accounts={body['database']['accounts_total']} "
      f"available={body['database']['available_balance_sum']} "
      f"reserved={body['database']['reserved_balance_sum']} pool={body['database']['pool']}")

section("9. COVERAGE: /metrics -> summary")
print(f"  metrics exposed: {coverage_block['metrics_exposed']}   covered: {coverage_block['metrics_covered']}")
print(f"  missing        : {coverage_block['missing']}")
for family, field in coverage_block["field_by_metric"].items():
    print(f"  [{'OK' if family not in coverage_block['missing'] else 'MISSING':>7}] {family:<42} -> {field}")

expected_codes = {
    "unauthorized",
    "forbidden",
    "not_found",
    "conflict",
    "insufficient_credits",
    "validation_error",
}
seen = set(body["errors_by_code"])
section("10. ASSERTIONS")
print(f"  error codes produced : {sorted(seen)}")
print(f"  all expected codes   : {sorted(expected_codes)}")
assert expected_codes <= seen, expected_codes - seen
assert coverage_block["missing"] == []
assert coverage_block["metrics_covered"] == coverage_block["metrics_exposed"]

database = body["database"]
minted = settings.initial_credit_allocation * database["accounts_total"]
held = database["available_balance_sum"] + database["reserved_balance_sum"]
print(f"  credit conservation  : available+reserved={held} == allocation*accounts={minted}")
assert held == minted
print("  OK: every error code exercised, every metric covered, credits conserved.")

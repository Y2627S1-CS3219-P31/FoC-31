# Observability (system-wide N2H)

Goal: use **measurement** to answer "what would make this service more
available", instead of guessing. The implementation is shared — one library,
one set of conventions — and today it is installed in **credit-service,
user-service and supplier-service**; the broker metrics they depend on are
scraped too. No frontend work: everything below is reachable with `curl`,
Postman, Prometheus and Grafana.

```python
# onboarding a service (see shared/foc_shared/observability.py)
from foc_shared.observability import Observability

OBS = Observability("supplier-service", prefix="supplier")
OBS.install(app, readiness_session_dep=get_session)
```

That single call adds `/metrics`, `/health/ready`, the HTTP middleware
(route-template labels + `X-Request-Id`), and the request/log correlation.
Services with an error envelope additionally call
`OBS.record_error_code(route, code)` from their exception handlers.

| Service | Status | Prefix |
| --- | --- | --- |
| credit-service | ✅ metrics + readiness + JSON summary + all business/saga/consumer counters | `credit` |
| supplier-service | ✅ metrics + readiness + envelope `code` counters | `supplier` |
| user-service | ✅ metrics + readiness (no `code` label yet — it returns `{"detail"}`) | `user` |
| api-gateway | ⏳ edge-level audit not implemented (would duplicate service numbers) | — |
| order-service | ⏳ pending PR #10 (its routes are still changing) | — |
| notification-service | ⏳ scaffold (501 stubs, no Rabbit consumer yet) | — |

> Status: implemented for the three services above (metrics, structured logs,
> readiness, credit JSON summary, opt-in Prometheus/Grafana profile). Tracing is
> deliberately out of scope, see [§7 Known gaps](#7-known-gaps).

---

## 1. What is instrumented

| Layer | Signal | Where |
| --- | --- | --- |
| HTTP | request count, latency histogram, status, `service` label | `foc_shared/observability.py` (shared middleware) |
| HTTP errors | error-envelope `code` (`insufficient_credits`, `conflict`, ...) | service `errors.py` (the only layer that knows the code) |
| Business | reserve/amend/transfer/release outcomes, duplicate suppression | credit `app/services/credit_service.py` |
| Saga | Order Service task outcomes, retries exhausted | same (task happy/failure paths) |
| Events | publish count/latency per routing key, success vs failure | credit `app/services/publisher.py` |
| Consumer | messages by queue+result, requeue reasons, last-message timestamp, connection state | credit `app/services/consumer.py` |
| Resources | DB pool in-use/size/overflow, reserved & available credit totals, account count | credit `app/db.py`, summary endpoint |

Two design decisions worth knowing:

1. **Route templates, never raw paths.** `scope["route"].path` yields
   `/credits/{user_id}/balance`; using the request path would create one time
   series per user id and eventually kill Prometheus.
2. **`/metrics` and `/health*` are excluded** from HTTP metrics. Otherwise the
   docker healthcheck (every 10 s) and the scrape would show up as traffic and
   silently inflate QPS and availability.

---

## 2. Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/metrics` | none — internal only, scraped over `foc-net` | Prometheus exposition |
| `GET` | `/health` | none | unchanged: `{"status": "ok"}` (compose healthcheck) |
| `GET` | `/health/ready` | none | DB + broker readiness; `503` when degraded |
| `GET` | `/credits/observability/summary` | **admin** (via gateway: `/api/credits/observability/summary`) | the JSON "data display" block |

`/metrics` is not published through the API gateway on purpose: the gateway is
the only public entry point, and metrics are an internal operational surface.

### The JSON summary

```bash
TOKEN=...   # admin JWT from /api/users/login
curl -s localhost:8080/api/credits/observability/summary \
  -H "Authorization: Bearer $TOKEN" | jq .
```

Shape (abridged):

```json
{
  "service": "credit-service",
  "generated_at": "2026-10-18T06:24:10+00:00",
  "uptime_seconds": 812.44,
  "window": "since process start",
  "http": {
    "total_requests": 412,
    "requests_by_class": {"2xx": 388, "3xx": 0, "4xx": 24, "5xx": 0},
    "server_error_rate": 0.0,
    "availability": 1.0,
    "latency_seconds": {"p50": 0.012, "p95": 0.031, "p99": 0.402, "mean": 0.019},
    "routes": [
      {"method": "POST", "route": "/credits/reservations",
       "requests": 260, "error_responses": 20, "p95_seconds": 0.031}
    ]
  },
  "errors_by_code": {"insufficient_credits": 18, "conflict": 6},
  "business": {
    "reservations": {"accepted": 210, "rejected_insufficient_credits": 18, "conflict": 6},
    "transfers": {"ok": 30},
    "releases": {"ok": 180},
    "duplicate_suppressed": {"reservation": 6}
  },
  "saga": {"tasks": {"release:released": 4, "amend:amended": 1}, "retries_exhausted": {}},
  "events": {"published": {"CreditReservationAccepted": {"ok": 198, "failed": 0}},
             "failed_total": 0},
  "consumer": {"queues": [
    {"queue": "credit-service.order-events", "connected": true,
     "last_message_age_seconds": 2.31, "messages": {"ok": 12},
     "requeues": {"retry_scheduled": 0}}
  ]},
  "database": {"accounts_total": 42, "available_balance_sum": 3910,
               "reserved_balance_sum": 120,
               "pool": {"in_use": 1, "size": 5, "overflow": 0}},
  "slo": {"availability_target": 0.99, "availability_actual": 1.0,
          "server_error_rate": 0.0, "error_budget_remaining_fraction": 1.0},
  "health": {"status": "ok", "broker_connected": true, "broker_error": null,
             "stalled_queues": [], "stalled_after_seconds": 300.0}
}
```

Percentiles are interpolated from the histogram buckets, so they are estimates
(bucket width bounds the error) — good enough to pick a page, not a benchmark.

---

## 3. Metric reference

| Metric | Type | Labels |
| --- | --- | --- |
| `credit_http_requests_total` | counter | `method, route, status` |
| `credit_http_request_duration_seconds` | histogram | `method, route, status` |
| `credit_http_errors_total` | counter | `route, code` |
| `credit_reservation_ops_total` | counter | `outcome` |
| `credit_amendment_ops_total` | counter | `outcome` |
| `credit_transfer_ops_total` | counter | `outcome` |
| `credit_release_ops_total` | counter | `outcome` |
| `credit_duplicate_suppressed_total` | counter | `op` |
| `credit_saga_tasks_total` | counter | `kind, outcome` |
| `credit_saga_retries_exhausted_total` | counter | `kind` |
| `credit_event_publish_total` | counter | `routing_key, result` |
| `credit_event_publish_duration_seconds` | histogram | `routing_key` |
| `credit_consumer_messages_total` | counter | `queue, result` |
| `credit_consumer_requeues_total` | counter | `queue, reason` |
| `credit_consumer_last_message_unixtime` | gauge | `queue` |
| `credit_consumer_connected` | gauge | `queue` |
| `credit_db_pool_in_use` / `_size` / `_overflow` | gauge | — |
| `credit_reserved_balance_sum` / `credit_available_balance_sum` / `credit_accounts_total` | gauge | — |

**Outcome values.** `reservation`: `accepted`, `rejected_insufficient_credits`,
`conflict`. `transfer`: `ok`, `already_transferred`, `conflict`,
`rejected_no_courier_account`. `release`: `ok`, `already_released`, `conflict`.
`amendment`: `amended`, `unchanged`, `rejected_insufficient_credits`, `conflict`.
`duplicate_suppressed.op`: `reservation`, `transfer`, `release`, `release_task`,
`amend_task`, `task_result`. `consumer.result`: `ok`, `validation_error`,
`business_error`, `transient_error`, `routing_key_mismatch`.

---

## 4. The three "measurement → decision" stories

These are the point of the exercise: a metric is only useful if it changes an
action.

### Story 1 — the consumer that is alive but not consuming

```bash
# stop only the broker; the consumer keeps logging, connections drop
docker compose stop rabbitmq
# watch the async-path signals
curl -s localhost:8000/metrics | grep -E 'credit_(event_publish|consumer)'
```

- `credit_event_publish_total{result="failed"}` climbs, and
  `POST /credits/reservations` p95 jumps to ≈ 3 s while its **5xx rate stays 0**
  — the publisher connects with `timeout=3` *after* the reservation committed, so
  a broker outage becomes latency, not an error. Status-code monitoring alone
  would never see this.
- `credit_consumer_last_message_unixtime` stops advancing.
- **Decision:** publishing does not belong on the request path. Either add an
  outbox (as user-service already does for `UserRegistered`) or move the publish
  off the critical path. Also: prefer a short publish timeout + retry over a
  3 s stall.

### Story 2 — latency that adding replicas will not fix

```bash
scripts/load-credit.sh          # same user, concurrent reservations
```

- p95 on `POST /credits/reservations` rises, while `rate(process_cpu...)`-style
  host CPU stays low and `credit_db_pool_in_use` stays at/below `size`.
- The cause is the row lock on that one account (`SELECT ... FOR UPDATE`):
  requests queue, they do not compete for CPU.
- **Decision:** scaling credit-service horizontally does *not* help — the queue
  is in Postgres, not in the app. Shorten the critical section, serialise per
  user, or accept the queue and raise the SLO. `credit_db_pool_in_use` is the
  discriminator: if it is pinned at `size`, you need connections; if it is
  low while p95 rises, you need to look at locks.

### Story 3 — business errors are not availability errors

```bash
# 409s from insufficient funds are an economy signal, not an outage
curl -s localhost:8000/metrics | grep credit_http_errors_total
```

- `insufficient_credits` climbing means the 100-credit allocation or the reward
  pricing is unrealistic for real order values.
- `credit_saga_tasks_total{outcome="release_failed"}` and
  `credit_saga_retries_exhausted_total` are **RabbitMQ-only** rejections: they
  never touch HTTP, so gateway-level dashboards cannot see them at all.
- **Decision:** put business codes on their own panel (they have their own
  owner), and alert on the *saga* failures separately — a saga that gives up is
  a user-visible broken order, not a slow request.

---

## 5. Running it

```bash
# 1. the stack as usual
make up

# 2. optional observability profile (does not change `make up`)
make obs-up
#    Prometheus http://localhost:9090
#    Grafana    http://localhost:3000  (anonymous viewer; admin/admin)

# 3. generate traffic
TOKEN=$(curl -s -X POST localhost:8080/api/users/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@u.nus.edu","password":"Passw0rd!"}' | jq -r .access_token)
UID_=$(curl -s localhost:8080/api/users/me -H "Authorization: Bearer $TOKEN" | jq -r .id)
FOC_TOKEN=$TOKEN FOC_USER_ID=$UID_ make obs-load

# 4. read the numbers without Grafana
curl -s localhost:8000/metrics          # only via the compose network
curl -s -H "Authorization: Bearer $TOKEN" \
  localhost:8080/api/credits/observability/summary | jq .http
```

### Self-test without Docker

`scripts/observability-demo.py` runs the real app in-process (sqlite + a stubbed
AMQP transport) and drives every metric family to a non-zero value: all HTTP
error-envelope codes, every business outcome label, all six duplicate-suppression
OPS, all four saga outcomes, both retry-exhausted counters, all six event routing
keys (including publish failures), and every consumer branch. It then prints
`/metrics`, the JSON summary, and a coverage table proving the summary carries
100% of the exposed metric families.

```bash
credit-service/.venv/Scripts/python scripts/observability-demo.py   # Windows
credit-service/.venv/bin/python     scripts/observability-demo.py   # POSIX
```

It exits non-zero if an error code is missing, if any metric family is not
covered by the summary, or if credits are not conserved
(`available + reserved == allocation × accounts`).

Provisioned dashboard: `observability/grafana/dashboards/credit-service.json`
(7 rows: availability & latency, async/economy KPIs, route latency, error codes,
business outcomes, async path, resources). Datasource and dashboard provider are
provisioned from `observability/grafana/provisioning/`.

Alert rules: `observability/prometheus/alerts.yml` — 5xx rate, route p95, DB pool
saturation, consumer stalled (`time() - last_message > 300`), publish failures,
saga retries exhausted.

> Note: `docker compose` healthchecks still use `GET /health`. `GET
> /health/ready` is for humans and for orchestration that can tolerate a 503
> (it reports DB *and* broker).

---

## 6. Structured logs

`LOG_JSON=true` switches the `app` logger tree to one JSON object per line with
`ts, level, logger, message` plus the correlation context:

```json
{"ts":"2026-10-18T06:24:10.412+00:00","level":"INFO","logger":"app.services.credit_service",
 "message":"Provisioned credit account for user_id=u-1 with 100 credits",
 "request_id":"b1f0c0f4...","user_id":"u-1"}
```

`request_id` comes from the incoming `X-Request-Id` (generated if absent) and is
echoed back in the response header, so a metric spike → Grafana → log line is a
single grep. Consumer records additionally carry `order_id` / `task_id`, which is
how a saga failure is traced back to one order without touching the database.

Only the `app` logger is reconfigured: uvicorn keeps its own handlers, so
startup/access output is unchanged and nothing is duplicated.

---

## 7. Known gaps

- **No distributed tracing.** FastAPI + aio-pika can be instrumented
  (`opentelemetry-instrumentation-*`) and OTLP exported to a collector, but
  propagation lives in the *clients*: a span reaches the consumer only if the
  publisher injects `traceparent`. `user-service` / `order-service` do not, so a
  credit-only rollout would produce root-only consumer spans. RabbitMQ itself
  emits **broker metrics** (enabled here via `rabbitmq_prometheus`), not traces.
  Adding tracing means either instrumenting the other services too, or accepting
  single-service traces and documenting the cut.
- **credit-service has no outbox.** Reservation events are published
  best-effort (`publish_reservation_event` swallows failures), so a broker
  outage loses them; the new `failed` counter and `ConsumerLastMessage` gauge
  make that visible, but nothing retries it. A transactional outbox (like
  user-service's `event_outbox` + relay) is a separate backlog item.
- **Counters are process-lifetime.** They reset on restart and are not
  persisted; Grafana queries therefore use `rate(...)` / `increase(...)` over a
  window rather than raw totals.
- **Single instance assumption for the gauges.** `credit_reserved_balance_sum`
  is refreshed on summary/build calls and reads the whole table, which is fine
  for one replica; with several replicas the sum is still correct but redundant.
- **No tracing UI.** No Jaeger/Tempo in the profile, deliberately: metrics first,
  traces only once propagation exists end-to-end.

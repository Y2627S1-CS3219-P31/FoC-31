# credit-service

Manages the platform's **closed credit economy** (backlog: Credit Service;
project M5). Credits only circulate within the platform.

## Responsibilities (from backlog)

- **F1** one credit account per user, created on registration with an initial
  allocation (100); tracks **available** and **reserved** balances.
- **F2** reserve credits when an order is created (validate sufficient funds;
  move available → reserved; emit reservation success/failure events);
  **F2.3** amend the reservation when an order's reward changes.
- **F3** transfer reserved credits to the courier on order completion —
  **idempotent** (F3.2.1).
- **F4** release credits on cancellation (F4.1) / expiry (F4.2); keep reserved
  on courier withdrawal (F4.1.2).
- **F5** record + expose transaction history.

## Invariants (NFRs)

- Balance never negative (N1.1.1); reserved ≤ available (N1.1.2).
- Credit ops are atomic (N1.2.1) and safe under concurrency (N1.2.2).
- Users cannot modify their own balances (N2.1); all ops authenticated +
  authorized (N2.2).

## Events

Consumes order-lifecycle events from RabbitMQ (`app/services/consumer.py`)
using `foc_shared.events`. Idempotent handling required.

## Layout

```text
app/
├── main.py               # lifespan: init_db + start RabbitMQ consumer
├── config.py
├── db.py                 # engine + init_db (create_all)
├── errors.py             # ServiceError hierarchy + error-envelope handlers
├── api/
│   ├── deps.py           # require_identity (X-User-Id/X-User-Role), DI
│   └── routes/           # health, credits
├── services/
│   ├── credit_service.py # all credit business logic
│   ├── publisher.py      # publishes reservation events (best-effort)
│   └── consumer.py       # consumes order + user-registered events
├── observability/        # metrics, structured logs, readiness, JSON summary
├── models/               # CreditAccount, CreditReservation, CreditTransaction,
│                         # CreditTaskResult (task-id idempotency)
├── schemas/              # Pydantic DTOs + interop event copies
└── repositories/         # persistence (row-locking reads)
```

## HTTP API

Base path inside the service: `/credits` (the gateway forwards `/api/credits`
here). Caller identity comes exclusively from the gateway-injected
`X-User-Id` / `X-User-Role` headers; a missing role degrades to `client`.

| Method | Path | Authz | Maps to |
| ------ | ---- | ----- | ------- |
| `GET` | `/credits/{user_id}/balance` | owner or admin | F1.3 / F1.4 |
| `GET` | `/credits/{user_id}/transactions?limit&offset` | owner or admin | F5.2 |
| `POST` | `/credits/reservations` | `user_id` must match caller (or admin) | F2 |
| `POST` | `/credits/reservations/{id}/amend` | owner or admin | F2.3 |
| `POST` | `/credits/reservations/{id}/transfer` | owner or admin | F3 (sync path) |
| `POST` | `/credits/reservations/{id}/release` | owner or admin | F4 (sync path) |
| `GET` | `/credits/observability/summary` | admin | N2H: metrics JSON view |
| `GET` | `/metrics` | none (internal, scraped over `foc-net`) | N2H: Prometheus |
| `GET` | `/health/ready` | none | N2H: DB + broker readiness |

Request bodies are snake_case JSON: `{"user_id","order_id","amount"}` /
`{"amount"}` / `{"courier_id"}`. All error responses use the shared envelope
`{"code","message"}`. Status codes used:

- `200`/`201` success · `401` missing identity · `403` forbidden
- `404` unknown account/reservation · `409` `conflict` or
  `insufficient_credits` (F2.1.3) · `422` `validation_error`

## Events (RabbitMQ)

Consumes (idempotent redelivery handling):

| Exchange | Type | Routing key / event | Effect |
| -------- | ---- | ------------------- | ------ |
| `foc.user.events` | fanout | `UserRegistered` | provision account with initial allocation (F1.1) |
| `foc.order.events` | topic | `OrderCompleted` | transfer to courier (F3.2), idempotent (F3.2.1) |
| `foc.order.events` | topic | `CourierWithdrawn` | **no-op** — credits stay reserved (F4.1.2) |
| `foc.order.events` | topic | `OrderExpired` | release (F4.2.1); legacy event, no reply |
| `foc.order.events` | topic | `OrderDeletionRequested` | release + reply `CreditReleased` / `CreditReleaseFailed` (F4.1.1) |
| `foc.order.events` | topic | `OrderCancellationRequested` | release + reply `CreditReleased` / `CreditReleaseFailed` (F4.1.1) |
| `foc.order.events` | topic | `OrderUpdateRequested` | amend to the new reward + reply `CreditAmended` / `CreditAmendRejected` (F2.3) |
| `foc.order.events` | topic | `OrderApprovalRequested` | transfer to `courier_id` + reply `CreditTransferSucceeded` / `CreditTransferFailed` |

Publishes to `foc.credit.events` (topic, routing key = event type):

- `CreditReservationAccepted` (F2.1.4) / `CreditReservationRejected` (F2.1.5) —
  best-effort: a publish failure never rolls back the committed reservation.
- `CreditReleased` / `CreditReleaseFailed`, `CreditAmended` /
  `CreditAmendRejected` and `CreditTransferSucceeded` / `CreditTransferFailed` —
  the definitive answer to an Order Service task. The publish is **not**
  best-effort: a failure makes the consumer retry, so the saga always receives
  exactly one answer per `task_id`. The transfer reply carries only
  `event_type`, `task_id`, `order_id`, `reservation_id`, `timestamp`, `reason?`
  (Order validates it with `extra="forbid"`).

Task requests are idempotent by `task_id` (recorded in `credit_task_results`):
redelivery republishes the stored outcome instead of applying the release,
amendment or settlement twice. Transient failures are retried by republishing
the message with an incremented `x-retry-count` header; after
`EVENT_RETRY_LIMIT` attempts a definitive failure reply is published instead of
looping forever. The transport schemas for these request/reply events are
currently duplicated in
`app/schemas/interop.py` and will move to `shared/` once the Order Service
lands them.

## Invariant notes

- `N1.1.1` balances never negative — enforced by DB CHECK constraints plus
  sufficiency validation in the service.
- `N1.1.2` interpreted as "a reservation may not exceed available credits",
  checked on reserve (F2.1.1) and amend-increase (F2.3.1).
- `N1.2.1/N1.2.2` every operation commits atomically; account/reservation rows
  are read with `SELECT ... FOR UPDATE`; the unique `order_id` on reservations
  plus idempotent handlers prevent duplicate transfers.

## Observability (N2H)

Measurement-driven availability work, scoped to this service:

- `GET /metrics` — Prometheus exposition (scraped inside `foc-net`, never via
  the gateway): HTTP count/latency/status labelled by **route template**, error
  count by error-envelope `code`, business outcomes (reserve / amend / transfer
  / release), duplicate-suppression, saga task outcomes and retries exhausted,
  event publish success/failure, consumer message results, requeue reasons,
  last-message timestamp, DB pool occupancy and credit totals.
- `GET /health/ready` — DB + broker readiness (`503` when degraded).
  `GET /health` is unchanged.
- `GET /credits/observability/summary` (admin) — one JSON block for display:
  availability, p50/p95/p99 per route, error codes, business counters, saga,
  events, consumer freshness, pool, SLO/error budget.
- Structured JSON logs (`LOG_JSON=true`) carry `request_id` (echoed back as
  `X-Request-Id`), `user_id`, and `order_id` / `task_id` for consumed events.
- `make obs-up` starts the optional Prometheus + Grafana profile with a
  provisioned dashboard and alert rules; `make obs-load` generates traffic.
  `scripts/observability-demo.py` drives every metric family without Docker and
  prints a coverage table (see `docs/observability.md` §5).

Full write-up, metric reference and the three "metric → decision" stories:
[`docs/observability.md`](../docs/observability.md).

## Run

```bash
make up
make test-credit-service
```

Database: `credit-db` (PostgreSQL). Exposes `GET /health`.

> Status: **implemented** per the D1 backlog (Credit F1–F5, N1–N2) plus the
> observability N2H (metrics, structured logs, readiness, JSON summary).

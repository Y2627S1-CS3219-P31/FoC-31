<!-- AI-INFLUENCED: Sprint 1 implementation status documented with Codex. -->

# order-service

Manages the complete **lifecycle of an errand request** — creation, listing,
acceptance, courier assignment, pickup, delivery, completion, cancellation,
and expiry (backlog: Order Service; project M4).

## Responsibilities (from backlog)

- **F1** requester CRUD on own orders; creating an order reserves credits via
  the Credit Service and only becomes `OPEN` once reserved.
- **F2** courier-facing listing + accept; corner cases: only-open orders,
  cannot accept own order, single courier per order, ≤3 concurrent.
- **F3** courier flow: pickup → deliver → requester approve/complete; courier
  withdraw; requester cancel-before-pickup.
- **F4** cancel open orders when their supplier is deactivated (event-driven).
- **F5** lifecycle **state machine** — see `app/services/lifecycle.py`
  (status set: `OPEN, ACCEPTED, PICKED_UP, AWAITING_APPROVAL, COMPLETED,
  CANCELLED, EXPIRED`). Invalid transitions are rejected.
- **F6** periodic **expiry sweeper**; publishes `OrderExpired`.

## Events

Publishes order-lifecycle events to RabbitMQ (`app/services/events.py`) using
the shared schemas in `foc_shared.events`. Consumed by Credit + Notification.

## Layout

```text
app/
├── main.py
├── config.py
├── db.py
├── api/routes/        # health and order endpoints
├── services/          # lifecycle.py (state machine), events.py (publisher)
├── models/  schemas/  repositories/
```

## Run

```bash
make up
make test-order-service
```

Database: `order-db` (PostgreSQL). Exposes `GET /health`.

## Reward update recovery

`PATCH /orders/{order_id}` commits a pending update task and its `OrderUpdate`
event to `order_event_outbox` in one transaction, then returns `202` with the
task ID. Credit Service independently decides whether the reservation needs
amendment, then publishes `CreditAmended` or `CreditAmendRejected`. The separate
update-result consumer locks the update task by `task_id`, verifies its
reservation ID and any supplied order ID, then applies or rejects the update.
Order Service records `OrderUpdated` or `OrderUpdateFailed` in the same event
outbox as the task result. A failed final commit requeues the credit result;
rejection leaves the live order unchanged. `GET /orders/updates/{task_id}` lets
the requester poll the result. Pending orders cannot receive another edit, be
deleted, appear in the courier listing, or be accepted by a courier.

Every outbound Order Service event uses one `order_event_outbox` table and one
event worker. Workflow task tables store local state only; each task and its
initial event are committed together. The worker publishes all event types with
RabbitMQ confirmation and retries. Inbound release-result and update-result
consumers remain separate because their event contracts and local handlers
differ.

Existing Order databases need `alembic upgrade head` from `order-service/`
before starting this version. The migration moves unpublished task events into
`order_event_outbox`, renames workflow tables to `order_release_tasks` and
`order_update_tasks`, and removes their old publication state.

## Order acceptance (F2.6)

`POST /orders/{order_id}/accept` accepts an order and returns `200` with the
updated `OrderResponse`. No request body is needed. The endpoint requires the
gateway-injected `X-User-Id` and `X-User-Role: client`; the current shared roles
are `client` and `admin`, with clients acting as requesters or couriers.
The courier ID always comes from the trusted header.

Acceptance rejects missing orders (`404`), non-client roles (`403`), and state
conflicts (`409`): own orders, assigned couriers, non-`OPEN` orders, passed
deadlines, pending update tasks, any deletion task, or three existing ongoing
orders. `ACCEPTED`, `PICKED_UP`, and `AWAITING_APPROVAL` count as ongoing.
A pending update task blocks acceptance until its credit result is applied.

The service locks the order and takes a transaction-scoped PostgreSQL advisory
lock for the courier before checking the ongoing count. This prevents double
assignment and concurrent requests from exceeding the three-order limit.
Both assignment and an `OrderAccepted` event are saved in one transaction.
Database failures roll back both and return `500 order_acceptance_failed`.

The single event worker publishes committed records from `order_event_outbox` to the
existing `ORDER_EVENTS_EXCHANGE` with routing key `OrderAccepted`. It uses the
shared `OrderEvent` payload (`order_id`, `requester_id`, `courier_id`,
`timestamp`, and `event_type`) and persistent messages with broker confirmation.
Failed or unroutable publications remain pending for retry. The AMQP
`message_id` stays the same across retries; delivery is at least once, so
consumers should deduplicate by that ID. The event timestamp is the acceptance
time, not the retry time. The worker starts and stops with the application.

The `20261016_order_event_outbox` migration adds the event table, and the
`20261016_single_order_event_outbox` migration consolidates workflow task
publication state into it. Run `alembic upgrade head` inside `order-service`
before deployment; startup also creates missing tables for fresh installations.

### Acceptance verification

Run the service suite with `make test-order-service` from the repository root.
PostgreSQL concurrency and rollback tests are opt-in:

```bash
PYTEST_ADDOPTS='--postgres-url=postgresql+asyncpg://USER:PASSWORD@localhost:5432/TEST_DB' make test-order-service
```

Use a test database whose user can create schemas. Each test creates and drops
only its own randomly named schema. Without this option, PostgreSQL tests are
skipped; API, validation, and event retry tests still run.

## API

The order-service contract is documented in `docs/`:

- [`order-service-api.md`](../docs/order-service-api.md) — human-readable
  reference covering endpoints, authentication, data models, dependency
  workflows, errors, filtering, and versioning.

At runtime, FastAPI also serves the live specification at `/openapi.json` and
interactive documentation at `/docs`.

> Status: `POST /orders`, `GET /orders`, `GET /orders/{order_id}`,
> `PATCH /orders/{order_id}`, `DELETE /orders/{order_id}`,
> `POST /orders/{order_id}/cancel`, and
> `POST /orders/{order_id}/accept` are implemented. Remaining lifecycle
> operations belong to later sprints.

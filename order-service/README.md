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
- **F6** expiry sweeper runs every five seconds, expires due orders in batches,
  and publishes `OrderExpired`.

## Events

Publishes order-lifecycle events to RabbitMQ (`app/services/events.py`) using
the shared schemas in `foc_shared.events` and Order-owned event schemas.
Withdrawal publishes the shared `CourierWithdrawn` fact, which matches the
existing Credit Service binding. Credit keeps the reservation held.

## Courier pickup and withdrawal

`POST /orders/{order_id}/pickup` requires the assigned courier and moves an
`ACCEPTED` order to `PICKED_UP`. `POST /orders/{order_id}/withdraw` requires the
assigned courier plus an `Idempotency-Key` header of 1–128 characters and moves
an `ACCEPTED` order back to `OPEN`. Both actions lock the order row, reject a
pending terminal action, and commit their lifecycle fact to the outbox with the
state change. Withdrawal leaves the credit reservation unchanged.

Successful withdrawal requests are saved in `order_requests`. Retrying with the
same key, order, and courier returns the original response without another
state change or event, even if the order has since been accepted again. Reusing
the key for a different request returns a conflict. The outbox worker retries
broker publication.

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

`PATCH /orders/{order_id}` commits a pending update task and its
`OrderUpdateRequested` event to `order_event_outbox` in one transaction, then
returns `202` with the task ID. Credit Service independently decides whether the
reservation needs amendment, then publishes `CreditAmended` or
`CreditAmendRejected`. The separate update-result consumer locks the update task
by `task_id`, verifies its reservation ID and any supplied order ID, then
applies or rejects the update.
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

### Expiry workflow (F6)

The expiry sweeper selects up to 100 open orders whose deadlines have passed,
oldest deadline first, using row locks with `SKIP LOCKED`. Each batch rechecks
eligibility, marks its orders `EXPIRED`, and writes one `OrderExpired` fact per
order to `order_event_outbox` in the same transaction. It immediately processes
another batch until none remain, then waits for the next five-second sweep.
Expiry does not create a workflow task or wait for a Credit Service result.
Credit Service consumes the `OrderExpired` fact and owns reservation-release
retries. The sweeper logs the structured signal
`order_expiry_slo_breached` when an open order is overdue by more than 20
seconds.

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
publication state into it. The `20261017_order_expiry_index` migration adds a
partial index for due open orders. Run `alembic upgrade head` inside `order-service`
before deployment; startup also creates missing tables for fresh
installations.

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

### Assigned orders (F3)

`GET /orders/assigned` lists the authenticated courier's ongoing assigned
orders. It requires the gateway-injected `X-User-Id` and
`X-User-Role: client` headers; courier identity is taken from `X-User-Id`.
The response is an array of `OrderResponse` objects for orders in `ACCEPTED`,
`PICKED_UP`, or `AWAITING_APPROVAL` status, sorted by deadline and then order
ID. An empty list returns `200` with `[]`. The endpoint reads only the
Order Service database and publishes no event.

### Participant order lists

`GET /orders/requested/ongoing` lists orders created by the authenticated
requester in `OPEN`, `ACCEPTED`, `PICKED_UP`, or `AWAITING_APPROVAL` status,
ordered by deadline and then order ID. `GET /orders/requested/completed`
lists that requester's `COMPLETED` orders. `GET /orders/assigned/completed`
lists `COMPLETED` orders assigned to the authenticated courier and, like
`GET /orders/assigned`, requires `X-User-Role: client`. Completed lists are
ordered by creation time, newest first, then order ID. All three endpoints
filter by the gateway-injected `X-User-Id`, return `OrderResponse` summaries
without photo data or the private S3 key, return `[]` when empty, and publish
no events. Use `GET /orders/{order_id}` to view an order's details and photo.

Available-order discovery (`GET /orders`) excludes orders whose deadline is
at or before the database's current time. This keeps overdue orders out of
the listing even before the expiry sweeper marks them `EXPIRED` (F2.4,
F2.4.1).

### Mark delivered (F3.1)

`POST /orders/{order_id}/deliver` marks an assigned order as delivered and
moves it from `PICKED_UP` to `AWAITING_APPROVAL`. It accepts gateway-injected
`client` and `admin` roles, but the caller's `X-User-Id` must match the
assigned courier. The request must include a multipart `photo` file: JPEG,
PNG, or WebP, no larger than 5 MiB or 20 million pixels. The service checks
the actual image format and decodes it before upload. It stores the private
S3 object key with the order update and `OrderDelivered` outbox record in one
database transaction. `awaiting_approval_at` starts the 24-hour approval
clock. The event worker publishes only after commit. Missing or invalid
photos, and S3 failures, leave the order unchanged and publish no event.
If the database commit fails after upload, the service attempts to delete
the unreferenced S3 object.

Set `ORDER_PHOTO_BUCKET` to a private bucket and `ORDER_PHOTO_REGION` to its
region. The workload's AWS identity needs `s3:PutObject`, `s3:GetObject`, and
`s3:DeleteObject` for delivery photos. The database backup bucket in the
separate infrastructure archive is not configured for this purpose. Run
`alembic upgrade head` before deploying to add the nullable photo-key column.

`GET /orders/{order_id}` allows the requester or the assigned courier and
returns the normal order fields plus `proof_of_delivery_photo`. This field is
`null` before delivery and otherwise contains a `data:image/...;base64,...`
URI that the frontend can display directly. The S3 key itself is never
returned. The response uses `Cache-Control: private, no-store`. The open-order
listing still contains no photo. Order detail downloads the photo on each
request, so its response is larger and depends on S3 being available.

At runtime, FastAPI also serves the live specification at `/openapi.json` and
interactive documentation at `/docs`.

### Approve delivered order (F3.5)

`POST /orders/{order_id}/approve` starts approval for the authenticated
requester's order when its status is `AWAITING_APPROVAL`. It returns `202`
with a task ID after saving the pending task and `OrderApprovalRequested`
event to the outbox in one transaction. The Order Service consumes
`CreditTransferSucceeded` or `CreditTransferFailed` from the Credit Service.
Each result is correlated to its pending task and applied in one transaction
with the resulting `OrderApproved` or `OrderApprovalFailed` outbox event.
Failed transfers leave the order awaiting approval. Run `alembic upgrade head`
to create the approval-task table in an existing database.

An auto-approval sweeper checks due orders every minute in batches of 100. It
locks each order and commits `COMPLETED` with an `OrderApproved` outbox event
without waiting for Credit. If no transfer task is pending, it also records a
task and `OrderApprovalRequested` event; an existing pending task is reused to
avoid a second transfer request. Credit results for these already completed
orders update only the transfer task, even when the transfer fails. Requester
approval still waits for a successful transfer before completing the order.
This allows an automatically approved order to remain `COMPLETED` while its
credit transfer needs separate recovery. The Credit Service must subscribe to
`OrderApprovalRequested` and publish transfer outcomes for that integration.
Apply the latest migration to add the indexed `awaiting_approval_at` column.
Existing awaiting orders recover their delivery time from retained
`OrderDelivered` outbox events where possible; otherwise their 24-hour clock
starts at migration time.

> Status: `POST /orders`, `GET /orders`, `GET /orders/assigned`,
> `GET /orders/requested/ongoing`, `GET /orders/requested/completed`,
> `GET /orders/assigned/completed`,
> `GET /orders/{order_id}`,
> `PATCH /orders/{order_id}`, `DELETE /orders/{order_id}`,
> `POST /orders/{order_id}/cancel`, and
> `POST /orders/{order_id}/accept`, `POST /orders/{order_id}/deliver`, and
> `POST /orders/{order_id}/approve` are implemented. Remaining lifecycle
> operations belong to later sprints.

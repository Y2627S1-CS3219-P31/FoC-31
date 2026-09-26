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
├── api/routes/        # health and order HTTP endpoints
├── services/          # lifecycle.py (state machine), events.py (publisher)
├── models/  schemas/  repositories/   # stubs
```

## Run

```bash
make up
make test-order-service
```

Database: `order-db` (PostgreSQL). Exposes `GET /health`.

Implemented first-slice endpoints: create, available-order listing, requester
detail lookup, and requester deletion. Remaining lifecycle actions (accept,
pickup, delivery, completion, cancellation events, and expiry sweeper) are
still pending.

# notification-service

Delivers notifications to users in response to **order-lifecycle events**
(backlog: Notification Service). This is the primary **event-driven** consumer
in the system (project M6).

## Responsibilities (from backlog)

- **F1** subscribe to Order Service events — `OrderAccepted`, `OrderPickedUp`,
  `OrderDelivered`, `OrderCompleted`, `OrderCancelled`, `CourierWithdrawn`,
  `OrderExpired`; consume asynchronously; persist per recipient.
- **F2** notify the **requester** of progress on their orders.
- **F3** notify the **courier** of changes to assigned orders.
- **F4** notify **both** parties on supplier-deactivation cancellation.

## Reliability (NFRs)

- No duplicate user-visible notifications on redelivery (N1.1).
- Delivery delay/failure must not block the underlying order/credit op
  (N2.1) — events are consumed asynchronously.

## N2H hook

`app/services/consumer.py` is structured with a pluggable delivery channel so
real-time push (WebSocket/SSE — NTH2) can be added without re-architecting.

## Layout

```text
app/
├── main.py
├── config.py
├── db.py
├── api/routes/        # health, notifications (stubs)
├── services/          # consumer.py (order-event handler)
├── models/  schemas/  repositories/   # stubs
```

## Run

```bash
make up
make test-notification-service
```

Database: `notification-db` (PostgreSQL). Exposes `GET /health`.

> Status: **scaffold**. Endpoints return `501 Not Implemented` until built.

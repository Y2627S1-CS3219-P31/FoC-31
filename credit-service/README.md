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
├── main.py
├── config.py
├── db.py
├── api/routes/        # health, credits (stubs)
├── services/          # consumer.py (order-event handler)
├── models/  schemas/  repositories/   # stubs
```

## Run

```bash
make up
make test-credit-service
```

Database: `credit-db` (PostgreSQL). Exposes `GET /health`.

> Status: **scaffold**. Endpoints return `501 Not Implemented` until built.

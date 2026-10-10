# Event Catalog

Canonical list of asynchronous events (project M6). Schemas live in
`shared/foc_shared/events.py` so all parties share one contract. Consumers must
handle redelivery **idempotently**.

Broker: RabbitMQ. There are two exchanges:

- `foc.user.events` (**fanout**) — published by User Service.
- `foc.order.events` (**topic**, routing key = event type) — published by
  Order Service (PR #5).

## User events — `foc.user.events` (fanout)

| Event | Published when | Publisher | Consumed by | Payload (`foc_shared.events`) | Effect |
| ----- | -------------- | --------- | ----------- | ----------------------------- | ------ |
| `UserRegistered` | Email OTP verified (register → verify) | User Service, via a transactional outbox + background relay (`user-service/app/services/events.py`) | Credit Service (`credit-service/app/services/consumer.py`) | `event_type` (`"UserRegistered"`), `user_id`, `email`, `timestamp` (`UserRegisteredEvent`) | Provision the new account's initial balance (`INITIAL_CREDIT_ALLOCATION`, Credit F1.1). |

This is the one async flow already implemented on `main`: verification writes an
`event_outbox` row in the same transaction that sets `email_verified`, and the
relay publishes it to the fanout exchange (see
`user-service/docs/flowchart.md` §5).

## Order events — `foc.order.events` (topic)

Publisher = Order Service (**planned, PR #5**); consumers = Credit Service and
Notification Service. Routing key = event type.

| Event | Published when (backlog) | Consumed by | Effect |
| ----- | ------------------------ | ----------- | ------ |
| `OrderAccepted` | Courier accepts (F2.6.1) | Notification | Notify requester |
| `OrderPickedUp` | Courier picks up (F3.4.1) | Notification | Notify requester |
| `OrderDelivered` | Courier marks delivered (F3.1.1) | Notification | Notify requester |
| `OrderCompleted` | Requester approves / auto (F3.5.1) | Credit, Notification | Transfer credits; notify both |
| `OrderCancelled` | Requester cancels / supplier deactivation (F3.3.1, F4.1.3) | Credit, Notification | Release credits; notify |
| `CourierWithdrawn` | Courier withdraws (F3.2.2) | Credit, Notification | Keep credits reserved; notify requester |
| `OrderExpired` | Sweeper finds expired (F6.1.1) | Credit, Notification | Release credits; notify requester |

## Order event envelope (scaffold)

See `OrderEvent` in `foc_shared.events`:

- `event_type`, `order_id`, `requester_id`, `courier_id?`, `timestamp`,
  `reason?`

TODO (team): finalize per-event payload fields (order name, new status, reward
amount) and whether ordering matters for each flow.

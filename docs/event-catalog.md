# Event Catalog

Canonical list of asynchronous events (project M6). Publisher = Order Service;
consumers = Credit Service and Notification Service. Schemas live in
`shared/foc_shared/events.py` so all parties share one contract.

Broker: RabbitMQ. Exchange: `foc.order.events` (topic). Routing key = event
type. Consumers must handle redelivery **idempotently**.

| Event | Published when (backlog) | Consumed by | Effect |
| ----- | ------------------------ | ----------- | ------ |
| `OrderAccepted` | Courier accepts (F2.6.1) | Notification | Notify requester |
| `OrderPickedUp` | Courier picks up (F3.4.1) | Notification | Notify requester |
| `OrderDelivered` | Courier marks delivered (F3.1.1) | Notification | Notify requester |
| `OrderCompleted` | Requester approves / auto (F3.5.1) | Credit, Notification | Transfer credits; notify both |
| `OrderCancelled` | Requester cancels / supplier deactivation (F3.3.1, F4.1.3) | Credit, Notification | Release credits; notify |
| `CourierWithdrawn` | Courier withdraws (F3.2.2) | Credit, Notification | Keep credits reserved; notify requester |
| `OrderExpired` | Sweeper finds expired (F6.1.1) | Credit, Notification | Release credits; notify requester |

## Event envelope (scaffold)

See `OrderEvent` in `foc_shared.events`:

- `event_type`, `order_id`, `requester_id`, `courier_id?`, `timestamp`,
  `reason?`

TODO (team): finalize per-event payload fields (order name, new status, reward
amount) and whether ordering matters for each flow.

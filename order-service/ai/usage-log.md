<!-- AI-INFLUENCED: Order-service implementation exchange recorded with Codex. -->

# AI usage log — Order Service

## 2026-10-16 — F2.6 courier acceptance

User request: “For F2.6, tell me the pseudocode. Remember that it has to check
whether this order's task in the outbox is pending before it can allow so that
is part of the validation.”

Codex read the supplied Sprint 2 requirements and existing order-service code,
then supplied pseudocode covering availability, self-acceptance, pending
updates, deletion tasks, the three-order limit, courier assignment, atomic
event recording, and retriable publication. It stated that awaiting-approval
orders count as ongoing and that a published amendment remains blocking while
its task is pending.

User approval: “okay implement this. Make sure the code is neat, simple to
understand, and add clear comments where appropriate but don't overdo the
comments either. Make sure it follows the project's architecture.”

Codex implemented the approved flow within the existing route → service →
repository structure. Additions include the acceptance route, PostgreSQL
transaction locks, validation and domain error mapping, a durable lifecycle
event outbox, broker-confirmed publication and retry, startup integration,
migration, documentation, and API/unit/PostgreSQL integration tests. The
existing shared client role and OrderEvent schema are reused.

All source changes and this log are confined to order-service as explicitly
required by the user; the repository-wide AI log is outside the permitted
scope. Existing unrelated changes were preserved. The local ignored pytest
launcher was repaired because it pointed to a different checkout.

Validation: 107 tests passed, including 13 PostgreSQL integration tests, with
the three pre-existing blocked test modules excluded. Ruff lint and formatting
checks passed. The full suite still fails collection because the shared event
module lacks CreditReleaseResult and CreditAmendResult (the existing workers
also import OrderDelete and OrderAmendCredit, which are absent). This also
blocks application startup. Shared contracts were not modified because they
are outside the user's permitted scope. RabbitMQ publication was tested with
mocks; PostgreSQL locking and rollback were exercised against an isolated
temporary database, then the database was stopped and removed.

## 2026-10-16 — Stage acceptance only

User request: “okay stage all the changes that are only sufficient for the
order accept.” Codex staged acceptance-specific hunks and their required
outbox models, lookup functions, messaging/test dependencies, and parent
migration. Update/deletion workflow changes remain unstaged and working
files are preserved. An isolated export of the staged snapshot passed all
82 runnable tests, including the health test; 13 PostgreSQL integration tests
were skipped without a database URL. The snapshot does not import the
unstaged workers that depend on missing shared contracts.

## 2026-10-16 — Route credit-release outcomes to local order actions

User request: implement the Order Service RabbitMQ workflow that consumes a
credit-release outcome, matches its reservation ID to a pending local task,
and then deletes, cancels, or expires the order according to that task.

Codex generalized the deletion outbox into an Order Service release-task
outbox with local `delete`, `cancel`, and `expire` actions. The publisher sends
the corresponding `OrderDelete`, `OrderCancellationRequested`, or
`OrderExpired` domain event and does not request an operation from another
service. One
consumer validates the concrete `CreditReleased` and `CreditReleaseFailed`
events through the internal `CreditReleaseResult` model, locks the pending task
by reservation ID, and applies the local action transactionally. Cancellation
outcome events are recorded only after that credit result. Unknown and duplicate
results are acknowledged without changing an order, while a failed database
transaction leaves the RabbitMQ delivery retryable.

The implementation includes a migration from the legacy deletion table,
startup integration, repository queries, documentation, and tests for all
three actions, release failures, duplicates, rollback, publication payloads,
consumer acknowledgements, and legacy data migration. Changes remain confined
to `order-service/` as required. Validation: Ruff passed; 117 tests passed and
12 optional PostgreSQL tests were skipped because no PostgreSQL test URL was
provided.

## 2026-10-16 — Cancellation initiation and terminal-action handlers

User request: implement the supplied cancellation workflow and general
dispatcher pseudocode while keeping published events limited to facts from
the publishing service.

Codex added `POST /orders/{order_id}/cancel` with trusted requester identity,
ownership and lifecycle validation, pending-update and conflicting-action
guards, idempotent reuse of an existing pending cancellation, and durable
creation of a `cancel` release task. The Order action publisher emits
`OrderDelete`, `OrderCancellationRequested`, or `OrderExpired` facts.

The Credit outcome dispatcher now selects explicit delete, cancel, and expire
handlers from a handler map. Each handler locks and revalidates its order,
performs its local change, and completes or fails the task without publishing
a duplicate cancellation or expiry event.
Database failures roll back and cause RabbitMQ redelivery; unmatched and
duplicate outcomes remain safe no-ops. Validation: Ruff passed; 131 tests
passed and 12 optional PostgreSQL tests were skipped without a PostgreSQL URL.

## 2026-10-16 — Publish explicit cancellation request and outcome facts

User request: implement the approved cancellation workflow using
`OrderCancellationRequested` before Credit Service acts, followed by
`OrderCancelled` or `OrderCancellationFailed` after the credit outcome.

Codex changed the pending cancellation event to
`OrderCancellationRequested`. A matching `CreditReleased` now changes the
order to `CANCELLED`, completes the task, and records `OrderCancelled` in the
durable lifecycle outbox in one transaction. `CreditReleaseFailed` leaves the
order unchanged, marks the task failed with the reason, and records the local
`OrderCancellationFailed` outcome atomically. The lifecycle publisher now
validates and publishes both shared lifecycle events and the Order-owned
cancellation-failure contract. Duplicate results remain no-ops, while database
failures roll back the task, order, and outcome event before redelivery.

## 2026-10-16 — Publish explicit deletion request and outcome facts

User request: replace the pending `OrderDelete` event with
`OrderDeletionRequested`, then publish `OrderDeleted` or
`OrderDeletionFailed` after Order Service receives the corresponding credit
outcome.

Codex updated the deletion action publisher and added Order-owned deletion
outcome contracts. `CreditReleased` now deletes the order, completes its task,
and records `OrderDeleted` in the durable event outbox in one transaction.
`CreditReleaseFailed`, or a failed final deletion validation, leaves the order
unchanged, fails the task with its reason, and records
`OrderDeletionFailed`. The existing lifecycle-event worker publishes both
outcomes with broker confirmation and retry. Focused tests cover request
publication, both outcomes, parsing, and transaction rollback.

## 2026-10-16 — Reject conflicting deletion workflows

User request: make deletion retries idempotent only for an existing pending
deletion, while rejecting pending cancellation or expiry tasks, failed terminal
tasks, and orders whose state does not allow deletion.

Codex updated the deletion service to return an existing pending `delete` task,
reject a different pending terminal action with a state conflict, and retain the
existing failed-task and order-state guards. Focused tests cover idempotent
deletion retries, cancellation and expiry conflicts, and failed terminal tasks.

## 2026-10-16 — Publish final order-update outcomes

User request: publish `OrderUpdated` or `OrderUpdateFailed` after consuming the
corresponding `CreditAmended` or `CreditAmendRejected` result.

Codex added Order-owned update outcome contracts and records the matching event
in the durable lifecycle-event outbox. Applying the proposed order, completing
its task, and recording `OrderUpdated` now commit atomically. Rejecting the task
with its reason and recording `OrderUpdateFailed` also commit atomically. The
existing event worker validates and publishes both outcomes with broker
confirmation and retry. Tests cover success, rejection, duplicate handling,
parsing, and rollback of both the task result and outcome event.

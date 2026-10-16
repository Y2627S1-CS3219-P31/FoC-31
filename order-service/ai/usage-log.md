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

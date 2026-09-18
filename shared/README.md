# shared

Small shared Python library used across FoC backend services. It is **not** a
microservice — it is a library that services import to keep cross-cutting
contracts consistent.

Contents:

- `foc_shared/events.py` — event names + Pydantic schemas for the RabbitMQ
  order-lifecycle workflow (M6). These are the wire contracts between the
  Order Service (publisher) and the Credit / Notification services
  (consumers).
- `foc_shared/auth.py` — the trusted header contract (`X-User-Id`,
  `X-User-Role`) that the API Gateway injects and backend services read.
- `foc_shared/errors.py` — a common error-envelope shape so all services
  return consistent error responses.

## Usage

Services depend on this package via an editable/relative install. In each
service's `requirements.txt`:

```text
-e ../shared
```

In Docker, the shared package is copied into the image build context (see each
service's Dockerfile).

> NOTE: This is scaffolding only. Extend the event schemas and contracts as
> the team finalizes them during the sprints.

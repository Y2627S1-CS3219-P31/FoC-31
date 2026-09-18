# ADR 0001: Record Architecture Decisions

- Status: accepted
- Date: TODO

## Context

Per the CS3219 AI policy, architecture and design decisions must be made and
documented by the team (not outsourced to AI). We use lightweight Architecture
Decision Records (ADRs) to capture significant choices and their rationale.

## Decision

We record each significant architectural/design decision as a numbered
Markdown file in `docs/adr/`, using this template:

```
# ADR NNNN: <title>
- Status: proposed | accepted | superseded
- Date: <date>
## Context
## Decision
## Consequences
```

## Consequences

- Decisions and trade-offs are traceable for grading and onboarding.
- New decisions add a new ADR rather than editing history.

---

## Suggested ADRs to write (team-authored)

- Microservices vs modular monolith
- Database-per-service + choice of PostgreSQL
- RabbitMQ for the async/event-driven workflow
- Custom FastAPI API gateway for edge auth/RBAC
- Session credential format + lifetime

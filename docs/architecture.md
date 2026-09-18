# Architecture

> Placeholder for the FoC architecture documentation. Keep the diagram source
> here and export an image for slides/README.

## Style

Distributed, **domain-partitioned microservices** (per CS3219 L4/L6): each
business domain (User, Supplier, Order, Credit, Notification) is an
independently deployable service with its own database. Services are
internally **layered** (`api/routes` → `services` → `repositories`).

## Components

| Component | Responsibility | Data store | Sync/Async |
| --------- | -------------- | ---------- | ---------- |
| api-gateway | Single entry point; edge auth + RBAC; routing | — | sync (HTTP) |
| user-service | Registration, auth, RBAC, profile | user-db | sync + publishes events |
| supplier-service | Supplier CRUD, discovery, seeding | supplier-db | sync |
| order-service | Errand lifecycle + state machine | order-db | sync + publishes events |
| credit-service | Closed credit economy | credit-db | sync + consumes events |
| notification-service | User notifications | notification-db | consumes events |
| frontend | Responsive SPA (requester/courier/admin) | — | sync (HTTP) |
| rabbitmq | Event broker | — | async |

## Diagram

TODO: add a labelled architecture diagram (see L6 "Guidelines for Architecture
Diagrams": title, legend, explained elements, labelled relationships with
protocols). A text sketch lives in the root `README.md`.

## Key decisions (fill in — team-authored, not AI)

- Why microservices vs modular monolith.
- Database-per-service rationale.
- RabbitMQ as the async backbone; which flows are eventually consistent.
- API gateway as the sole public entry point.

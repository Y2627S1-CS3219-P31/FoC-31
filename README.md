# CS3219 — Software Design and Architecture (AY2627 Sem 1)

## Friend on Campus (FoC)

**Friend on Campus (FoC)** is a peer-to-peer campus errand platform where
students can request items to be collected from stores or facilities on
campus, and other students can fulfil (and deliver) those requests. The
platform runs on a closed credit economy — credits cannot be bought,
withdrawn, or exchanged for money, and only circulate within the platform.

---

## Team Members

| Name | Role / Ownership |
| ----- | ----- |
| _TBD_ | _TBD_ |
| _TBD_ | _TBD_ |
| _TBD_ | _TBD_ |
| _TBD_ | _TBD_ |
| _TBD_ | _TBD_ |

---

## Tech Stack

| Layer | Choice |
| ----- | ----- |
| Backend services | Python 3.12 + FastAPI |
| API Gateway | FastAPI reverse proxy (`httpx`) with edge auth + RBAC |
| Frontend | React + TypeScript + Vite (responsive SPA) |
| Databases | PostgreSQL — one instance per service (DB-per-service) |
| Async messaging | RabbitMQ (order lifecycle events) |
| Containerization | Docker + Docker Compose |
| Tooling | `ruff` (lint/format), `pytest` (tests), `make` (dev tasks) |

---

## Architecture

Distributed, domain-partitioned microservices. The client talks only to the
API Gateway, which authenticates requests at the edge and reverse-proxies to
the appropriate backend service. Order lifecycle changes are published as
events to RabbitMQ and consumed asynchronously by the Credit and Notification
services.

```text
                         ┌──────────────────────┐
        Browser  ──────▶ │   Frontend (React)   │
                         └──────────┬───────────┘
                                    │ HTTPS/JSON
                         ┌──────────▼───────────┐
                         │   API Gateway         │  edge auth + RBAC
                         │   (FastAPI)           │  (validates token,
                         └──────────┬───────────┘   injects trusted role)
        ┌──────────────┬───────────┼────────────┬───────────────┐
        ▼              ▼           ▼            ▼               ▼
  ┌───────────┐ ┌────────────┐ ┌─────────┐ ┌──────────┐ ┌───────────────┐
  │   user    │ │  supplier  │ │  order  │ │  credit  │ │ notification  │
  │  service  │ │  service   │ │ service │ │ service  │ │   service     │
  └─────┬─────┘ └─────┬──────┘ └────┬────┘ └────┬─────┘ └───────┬───────┘
        │             │             │           │               │
   ┌────▼───┐   ┌─────▼────┐   ┌────▼───┐  ┌────▼────┐    ┌──────▼──────┐
   │user-db │   │supplier- │   │order-db│  │credit-db│    │notification-│
   │  (PG)  │   │  db (PG) │   │  (PG)  │  │  (PG)   │    │  db (PG)    │
   └────────┘   └──────────┘   └────┬───┘  └────┬────┘    └──────▲──────┘
                                    │           │                │
                                    │  publish  │  consume       │ consume
                                    └──────────▶┌──────────┐◀────┘
                                                │ RabbitMQ │
                                                └──────────┘
```

See `docs/` for the event catalog, architecture-diagram source, and ADRs.

---

## Repository Structure

This repository follows a **one-service-per-folder** structure: each
microservice lives in its own top-level folder.

```text
.
├── api-gateway/          # single entry point; edge auth + routing
├── user-service/         # registration, auth, RBAC, profile
├── supplier-service/     # supplier CRUD, discovery, seeding
├── order-service/        # errand lifecycle + state machine + events
├── credit-service/       # closed credit economy (reserve/transfer/release)
├── notification-service/ # consumes order events, notifies users
├── frontend/             # React + Vite responsive SPA
├── shared/               # small shared Python lib (event schemas, contracts)
├── data/                 # provided supplier seed CSV + images
├── scripts/              # dev helper scripts (install/test/lint/wait)
├── docs/                 # architecture diagram, event catalog, ADRs
├── ai/                   # AI usage log (course policy)
├── Makefile              # developer entrypoint (see `make help`)
├── compose.yaml          # local containerized deployment
└── README.md
```

- Any **nice-to-have (N2H)** feature that warrants its own service should
  be added as an **additional folder** at the same level, following the
  same per-service structure.
- Files for agentic coding tools (e.g. agent configs, prompts, skills)
  may be added as needed, but must still **respect the
  one-service-per-folder skeleton** for core implementation.

---

## Quickstart

Prerequisites: Docker + Docker Compose. (For local, non-container dev:
Python 3.12 and Node 20+.)

```bash
# 1. Configure environment
cp .env.example .env      # then edit secrets as needed

# 2. Bring the whole stack up (build + run)
make up                   # == docker compose up --build -d

# 3. Check everything is healthy
make ps

# 4. Tail logs
make logs

# 5. Tear down
make down
```

Once up:

- Frontend: <http://localhost:5173>
- API Gateway: <http://localhost:8080> (health: `/health`)
- RabbitMQ management UI: <http://localhost:15672>

Run `make help` to see all available developer tasks.

---

## Development

Each backend service is a self-contained FastAPI app with a layered internal
structure (`api/routes` → `services` → `repositories`). See each service's
own `README.md` and `AGENTS.md`.

```bash
make install          # create venvs + install deps for every service
make test             # run pytest across all services
make test-user-service   # test a single service
make lint             # ruff check across services
make fmt              # ruff format across services
```

---

## AI Use Summary

Per the CS3219 AI Usage Policy (Project Document, Appendix 2), this section
consolidates AI tool usage for the project. Requirements elicitation and
architecture/design decisions were made by the team; AI assistance is limited
to boilerplate/scaffolding, implementation, debugging, refactoring, and docs.

- **Tools:** _TBD (record tool + model per use)_
- **Prohibited phases avoided:** requirements elicitation; architecture/design
  decisions.
- **Used for:** initial repository scaffolding and boilerplate generation.
- **Verification:** all AI outputs are reviewed, edited, and tested by the
  authors.
- **Prompts / key exchanges:** see [`ai/usage-log.md`](./ai/usage-log.md).

# supplier-service

Maintains information about campus **stores, facilities, and landmarks** from
which users may request errands, and exposes discovery + lookup APIs
(backlog: Supplier Service; project M3).

## Responsibilities (from backlog)

- **F1 CRUD** — admin create/update/deactivate supplier records
  (name, category from a predefined set, campus location).
- **F2 Discovery** — list active suppliers; filter by category and
  campus zone; case-insensitive keyword search on name + location.
- **F3 Detail** — retrieve a single supplier by id (incl. active/deactivated
  status); `404` with an explanatory message when missing.
- **F4 Seeding** — idempotent load of the provided baseline data
  (`data/csv/supplier-seed-data.csv`), plus room for additional entries.
- **F5 Service API** — retrieve/validate a supplier by id for other services
  (returns current status), with pagination.

## Layout

```text
app/
├── main.py            # app wiring + lifespan (init_db)
├── config.py
├── db.py              # async engine, session, init_db
├── errors.py          # error-envelope exception handlers
├── api/
│   ├── deps.py        # RBAC (require_admin) + service DI
│   └── routes/        # health, suppliers (CRUD)
├── models/            # Supplier ORM model
├── schemas/           # Pydantic DTOs (camelCase)
├── services/          # supplier_service.py + seeder.py
└── repositories/      # supplier_repo.py (persistence)
```

The seed CSV is mounted read-only at `/data/csv/supplier-seed-data.csv`
(see `compose.yaml`).

## Run

```bash
make up
make test-supplier-service
```

Database: `supplier-db` (PostgreSQL). Exposes `GET /health`.

## API

The supplier-service contract is documented in `docs/`:

- [`supplier-service-api.md`](../docs/supplier-service-api.md) — human-readable
  reference (endpoints, auth/RBAC, data model, errors, pagination, versioning).
- [`supplier-service-openapi.yaml`](../docs/supplier-service-openapi.yaml) —
  machine-readable OpenAPI 3.1 spec.

At runtime, FastAPI also serves the live spec at `/openapi.json` and
interactive docs at `/docs`.

> Status: **implemented**. List, detail, create, update, and deactivate are
> served at `/suppliers`; run `make seed` to load the baseline catalog. Public
> clients reach these through the API gateway at `/api/suppliers` — the gateway
> strips the `/api` prefix before forwarding to this service.

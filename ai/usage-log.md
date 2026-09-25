# AI Usage Log

Per the CS3219 AI Usage Policy (Project Document, Appendix 2). Record every
AI-assisted contribution here with timestamp, tool + model, scope, prompt(s),
and author review. Requirements elicitation and architecture/design decisions
must NOT be outsourced to AI.

Format for each entry:

```
## <date> — <author>
- Tool: <tool> (model: <model>)
- Scope: <what was generated/refactored/debugged/explained>
- Prompt(s): <exact prompt(s) + key responses, or a link>
- Author review: <how you validated/edited/tested the output>
```

---

## 18/09/2026 — John Gao Jiahao

- Tool: Claude Code (model: Opus)
- Scope: Initial repository skeleton scaffolding only (boilerplate — no business
  logic). Generated: per-service FastAPI app structure (config, db, api/routes,
  models/schemas/services/repositories, `/health`, smoke tests) for
  api-gateway, user-, supplier-, order-, credit-, and notification-service; the
  `shared/` contracts library (event schemas, auth-header contract, error
  envelope); Dockerfiles; `compose.yaml` (5 services + gateway + frontend + 5
  Postgres + RabbitMQ); `.env.example`, `.gitignore`; root/per-service
  `README.md` and `AGENTS.md`; `Makefile` + `scripts/`; React+Vite frontend
  shell (routing + placeholder pages); `docs/` templates; CI workflow.
  All product requirements and architecture/design decisions (microservices,
  DB-per-service, RabbitMQ, custom gateway, tech stack) were made by the team;
  the tool only implemented the chosen structure.
- Prompt(s):
  1. "With reference to [the D1 backlog PDF] and the lecture slides in the
     CS3219 folder, come up with a plan to create the skeleton repo from this
     repo that will allow the team to work on the project."
  2. Answered clarifying questions selecting the stack: Python + FastAPI
     backend, custom FastAPI API gateway, React + TypeScript + Vite frontend,
     PostgreSQL per service, RabbitMQ, runnable hello-world + full wiring,
     `requirements.txt` + venv, one Postgres container per service, generic
     ownership placeholders, standalone `ruff.toml` + `pytest.ini`, plus a
     `Makefile`/scripts for developer experience. "Do keep in mind our N2Hs."
  3. "Lets execute but remember to make a new branch."
- Author review: Reviewed all generated files. Verified `docker compose config`
  validates, `ruff check` passes across all Python packages, and `pytest`
  passes for every service (including the gateway's unknown-route → 404 test).
  Endpoints are intentionally stubbed (`501 Not Implemented`); business logic,
  auth/RBAC enforcement, and event wiring remain to be implemented and reviewed
  by the team.

## 25/09/2026 — John Gao Jiahao

- Tool: Claude Code (model: Claude Sonnet)
- Scope: supplier-service API documentation. The team designed and agreed on
  the endpoint set, field names, enums, and error codes for supplier-service. The tool was used only to write up that agreed design as a
  Markdown reference and an OpenAPI 3.1 YAML file, and to cross-check the two
  against each other and against the existing code and contracts for
  consistency. No endpoint, schema, or interface decisions were made by the
  tool.
- Prompt(s):
  1. "Here is our agreed endpoint spec for supplier-service:[Txt File]. Write this up as (a) a Markdown API reference
     and (b) an OpenAPI 3.1 YAML file, matching our existing docs style." → clarified to supplier-service only.
  2. "Cross-check the Markdown and YAML against each other and against the
     current supplier-service code/contracts for mismatches"
  3. "Implement the formatting fixes" (with a follow-up to hold off on committing pending
     review).
- Author review: Confirmed the Markdown and YAML match the team's agreed
  design exactly (no unrequested endpoints/fields). Verified the OpenAPI file
  parses as valid YAML/OpenAPI 3.1 and all $refs resolve. Not yet
  merged, pending final team review.

## 25/09/2026 — John Gao Jiahao

- Tool: OpenCode (model: Claude Sonnet)
- Scope: supplier-service implementation (backlog Supplier F1–F5). Implemented,
  under team-owned design decisions and the pre-agreed API contract: the
  Supplier ORM model + init_db; Pydantic DTOs (camelCase) with the locked
  Category enum; repository (CRUD, case-insensitive keyword search over
  name/building/location, category+zone filters, pagination); service layer
  (404/409/validation rules); RBAC dependency reading the gateway-injected
  X-User-Id/X-User-Role headers (admin-only create/update/deactivate);
  error-envelope exception handlers; /api/suppliers CRUD routes + app wiring
  (lifespan init_db); and the idempotent CSV seeder (backlog F4). Also added
  aiosqlite as a test dependency and a flake8-bugbear ruff setting for
  FastAPI DI defaults.

  Separately, while implementing against the existing docs/OpenAPI, the tool
  flagged four inconsistencies between those docs and the actual seed data /
  gateway routing: no `campusLocation` column in the CSV, a mismatched base
  path, an unlocked category enum, and PATCH/deactivate listed as planned
  rather than implemented. The team reviewed each and decided the resolution
  (see Prompt 2); the tool then applied only those team-decided resolutions
  to the docs and code. The tool did not choose the field name, base path,
  enum values, or which endpoints to implement — it surfaced the mismatch and
  the team resolved it.

  All product requirements and the endpoint/schema/error-code contract were
  decided by the team beforehand; the tool implemented that agreed design and
  did not make requirements or architecture decisions.

- Prompt(s):
  1. "Help me implement the supplier service based on the API spec and the
     documentation/architecture in the docs folder … this is for the D2
     milestone." (+ pointed the tool at the CS3219 docs and data.zip seed data.)
  2. Tool surfaced the four inconsistencies above; team discussed and decided:
     rename campusLocation→building (no such CSV column), keep the 4
     categories as-is, load the CSV bytes as-is, implement full CRUD incl.
     PATCH+deactivate, and mount routes at /api/suppliers to match the
     gateway (updating docs to match). These decisions were then given back
     to the tool to apply.
  3. "Use TDD, feel free to use subagent-driven development, commit at each
     step, keep commit messages succinct."
- Author review:
  I have reviewed all generated files against the team's agreed contract. Ran
  `make test-supplier-service` (46 passing) and `ruff check`/`format`
  (clean). Spot-checked the running service: RBAC 403 (non-admin) / 201
  (admin create), 422 on bad category, deactivate 200 then 409 on repeat,
  404 on missing supplier. Confirmed the idempotent seeder re-run produces
  0 new rows on a second pass (21 → 0). Confirmed docs/OpenAPI match the
  team-decided contract from Prompt 2.

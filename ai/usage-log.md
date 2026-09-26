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

---

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
  
---

## 26/09/2026 — Javier Enrique Wong

- Tool: Claude (claude.ai, model: Claude Sonnet 5)
- Scope: Documentation and test generation only, scoped to `api-gateway`.
  Updated `docs/architecture.md` and `docs/flowchart.md` (the internal
  layering diagram and the resolve → authorize → forward request pipeline)
  to match the current source code. Generated `tests/test_routing.py`
  (`resolve_upstream`'s known-prefix, unknown-prefix, and partial-segment
  boundary cases) and `tests/test_gateway.py` (`GatewayService`'s
  resolve/authorize/forward behavior, including the public-route,
  missing-token, invalid-token, and valid-token outcomes, and that
  `forward()` actually strips client-supplied `Authorization`/`X-User-*`
  headers before proxying). Also fixed a stale import path in
  `tests/test_auth.py` (`app.auth` → `app.services.auth`). No architecture
  or design decisions were made by the tool — the docs describe layering
  and behavior that already existed in the code.
- Prompt(s):
  1. "Given this architecuture.md and flowchart.md update based on the
     source code."
  2. "Also generate pytest:  `test_routing.py` covering `resolve_upstream`,
     unknown-prefix, and partial-segment cases and `test_gateway.py` 
     covering `GatewayService` resolve, authorize, forward behavior, and 
     fix `test_auth.py` below."
- Author review: Reviewed `docs/architecture.md`/`flowchart.md` against the
  actual resulting file layout for accuracy. Ran the generated suite and
  confirmed every test passes; checked that no test asserts on behavior the
  code doesn't actually implement.
  
- Tool: Claude (claude.ai, model: Claude Sonnet 5)
- Scope: Generated `api-gateway/docs/api-contract.md` from the existing gateway 
  routes, routing table, authentication behavior, path rewriting, CORS settings, 
  and error responses
- Prompt(s): "generate api-contract.md for api-gateway based on below"
- Author review: Compared the contract against `proxy.py`, `routing.py`, `auth.py`,
  `gateway.py`, and gateway configuration, then corrected the documentation to 
  distinguish gateway `/api/...` routes from backend routes.
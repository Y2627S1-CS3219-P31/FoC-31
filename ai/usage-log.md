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

## 25/09/2026 — Javier Enrique Wong

- Tool: Claude (claude.ai, model: Claude Sonnet 5)
- Scope: Documentation generation only, scoped to `user-service/docs/`
  (`architecture.md` and `flowchart.md`). The tool wrote the prose (component
  tables, explained-elements bullets) and Mermaid diagrams describing
  user-service's existing internal layering (`api/routes` → `services` →
  `repositories` → `models`), its two external boundaries (`user-db`,
  RabbitMQ), and its auth/OTP request flows. No architecture or design
  decisions were made by the tool — the layering convention, component
  boundaries, and models (`EmailOtp`, later renamed `OtpCode`, and `User`)
  were already implemented in the code by the team beforehand. The docs were
  regenerated a second time after the source code changed, purely to bring
  the documentation back in sync — the tool re-read the existing `app/`
  source and updated the write-up and diagrams to match, again without
  introducing any new design decisions.
- Prompt(s):
  1. "Draw out architecture.md and flowchart.md" — with the `api/` and
     `services` layers, and the `EmailOtp` and `User` models, described 
     to the tool in a table.
  2. "Update architecture.md and flowchart.md based on the source code."
  3. "Update this usage-log.md."
  4. "make commit msg for all my changes"
- Author review: Regenerated `architecture.md` and `flowchart.md` against the
  current source code and reviewed both against `app/` for accuracy.

- Tool: Claude (claude.ai, model: Claude Sonnet 5)
- Scope: Test generation only, scoped to `user-service/tests/`: `conftest.py`
  (per-test isolated sqlite fixture instead of the real Postgres, and a
  mocked RabbitMQ publish so tests don't need a live broker), `test_auth.py`
  (unit coverage for the token-verification and trusted-header-building
  helpers), and `test_user_flow.py` (register → verify/resend-otp → login →
  profile, covering the happy path plus validation, conflict, and
  auth-failure branches). No new behavior, validation rules, or design
  decisions were introduced by the tool — every assertion targets logic
  already implemented in `app/services/user.py` and
  `app/api/routes/users.py`; the tool only wrote pytest coverage for it.
- Prompt(s):
  1. "Write pytest for user Service: register, login, OTP
     verify, resend, and profile, including reregister while unverified
     and already verified, plus a fixture so the suite runs
     against isolated DB and mocked rabbitMQ publish instead of
     the real psql."
- Author review: Ran the generated suite against the current implementation
  and confirmed every test passes; checked that no test asserts on behavior
  the code doesn't actually implement.
  
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
- Scope: Helped understanding the transactional outbox pattern 
  for reliable RabbitMQ event delivery; implementing secure, idempotent 
  first-admin bootstrap on application startup; OTP rate limiting, 
  failed-attempt tracking, and temporary lockout behavior; 
  updating `user-service/docs/api-contract.md` with endpoint paths, 
  request bodies, headers, response payloads, validation rules, 
  and status codes; and updating user-service and API gateway tests 
  to match the `/users` internal prefix
- Prompt(s):
  1. "Explain the outbox pattern and how to implement"
  2. "How should OTP rate limiting and failed-attempt handling be
     implemented?"
  3. "Update `api-contract.md` to document current API request and
     response contracts based on the source code"
  4. "Help update pytest after the code changes"
- Author review: Reviewed the generated explanations and code changes,
  checked and verified that the updated Python files compile successfully.
  Reviewed api-contracts as well.
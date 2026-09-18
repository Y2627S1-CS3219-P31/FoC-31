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

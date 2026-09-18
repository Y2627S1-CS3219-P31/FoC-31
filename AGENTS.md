# AGENTS.md — Monorepo Conventions (FoC)

Guidance for humans and agentic coding tools working in this repository.
Per-service specifics live in each service's own `AGENTS.md`.

## Repository shape

- One microservice per top-level folder (see root `README.md`).
- Shared, non-service code lives in `shared/` (imported as a library).
- Never break the one-service-per-folder skeleton for core implementation.

## Tech + tooling

- Backend + gateway: Python 3.12, FastAPI. Deps in each service's
  `requirements.txt`; use a per-service `venv`.
- Frontend: React + TypeScript + Vite.
- Lint/format: `ruff` (config: per-service `ruff.toml`).
- Tests: `pytest` (config: per-service `pytest.ini`).
- Dev tasks: the root `Makefile` is the single entrypoint (`make help`).

## Conventions

- Every backend service exposes `GET /health` returning `{"status": "ok"}`.
- Backend services listen on port `8000` inside their container.
- Services never talk to each other's databases (DB-per-service).
- Cross-service sync calls go through documented HTTP APIs; async workflows
  go through RabbitMQ using event schemas defined in `shared/`.
- The API Gateway is the only public entry point. Backend services trust the
  `X-User-Id` / `X-User-Role` headers injected by the gateway and must not
  accept client-asserted roles.
- Configuration comes from environment variables (see `.env.example`);
  never hardcode secrets. Every new env var must be added to `.env.example`
  with a safe placeholder.

## Ownership map

Fill in as the team assigns services. Keep this current — it aids grading of
individual contributions.

| Area | Owner(s) |
| ----- | ----- |
| api-gateway | _TBD_ |
| user-service | _TBD_ |
| supplier-service | _TBD_ |
| order-service | _TBD_ |
| credit-service | _TBD_ |
| notification-service | _TBD_ |
| frontend | _TBD_ |
| shared / infra / CI | _TBD_ |

## AI usage

- Allowed: implementation, boilerplate, debugging, refactoring, docs.
- Not allowed: requirements elicitation, architecture/design decisions.
- Add a file-header attribution comment to every AI-influenced file and log
  prompts/exchanges in `ai/usage-log.md` (see Project Document, Appendix 2).

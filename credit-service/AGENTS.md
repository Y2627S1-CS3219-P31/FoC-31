# AGENTS.md — credit-service

See the root `AGENTS.md` for monorepo-wide conventions.

## Service specifics

- FastAPI app; entrypoint `app.main:app`, port `8000` in-container.
- Owns its own PostgreSQL database (`credit-db`). Never access another service's DB.
- Exposes `GET /health` returning `{"status": "ok"}`.
- Derive caller identity/role from the gateway-injected `X-User-Id` /
  `X-User-Role` headers (see `foc_shared.auth`). Never trust client-asserted
  roles.
- Credit ops must be atomic and idempotent; balance never negative; reserved
  <= available. Consume order events via foc_shared.events.

## Layers

`api/routes` (HTTP) → `services` (business logic) → `repositories`
(persistence). Keep HTTP concerns out of `services`.

## AI usage

Add a file-header attribution comment to every AI-influenced file and log
prompts in `../ai/usage-log.md`.

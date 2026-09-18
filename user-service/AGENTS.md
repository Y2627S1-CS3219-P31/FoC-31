# AGENTS.md — user-service

See the root `AGENTS.md` for monorepo-wide conventions.

## Service specifics

- FastAPI app; entrypoint `app.main:app`, port `8000` in-container.
- Owns its own PostgreSQL database (`user-db`). Never access another
  service's DB.
- Exposes `GET /health` returning `{"status": "ok"}`.
- Derive caller identity/role from the gateway-injected `X-User-Id` /
  `X-User-Role` headers (see `foc_shared.auth`). Never trust client-asserted
  roles.
- Passwords must be stored hashed (backlog N1.1); OTP codes expire within
  5 minutes (N1.2); sessions valid 60 minutes (N1.3).
- Publishes `UserRegistered` to RabbitMQ for downstream credit provisioning.

## Layers

`api/routes` (HTTP) → `services` (business logic) → `repositories`
(persistence). Keep HTTP concerns out of `services`.

## AI usage

Add a file-header attribution comment to every AI-influenced file and log
prompts in `../ai/usage-log.md`.

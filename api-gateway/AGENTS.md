# AGENTS.md — api-gateway

See the root `AGENTS.md` for monorepo-wide conventions.

## Service specifics

- FastAPI app; entrypoint `app.main:app`, port `8000` in-container, published
  on the host as the ONLY public entry point.
- Reverse-proxies to backend services via `httpx` using the route table in
  `app/routing.py`. Unknown routes must return `404`.
- Validates session credentials at the edge (`app/auth.py`) and injects
  trusted `X-User-Id` / `X-User-Role` headers. It MUST strip any
  client-supplied auth/identity headers to prevent role spoofing.
- Has no database of its own.
- Add new backend routes by extending `ROUTE_TABLE`, not by exposing services
  directly.

## AI usage

Add a file-header attribution comment to every AI-influenced file and log
prompts in `../ai/usage-log.md`.

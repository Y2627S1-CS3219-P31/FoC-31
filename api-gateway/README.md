# api-gateway

The **single public entry point** for the platform. It routes external client
requests to the correct backend service and enforces authentication +
role-based authorization at the edge (backlog: API Gateway).

## Responsibilities (from backlog)

- **F1 Routing** — route by path to the right backend (`app/routing.py`);
  reject unknown routes with `404` (F1.1.1); backends are never exposed
  directly (only the gateway is published).
- **F2 Authentication** — validate the caller's session credential on every
  protected route before routing (F2.1); reject missing/malformed/expired
  (F2.1.1); verify against the User Service (F2.1.2). See `app/auth.py`.
- **F3 Authorization (RBAC)** — derive the caller's role from the validated
  credential and forward it via trusted `X-User-Id` / `X-User-Role` headers
  (F3.1). **Client-asserted roles are stripped** (F3.1.1); admin-only routes
  are rejected for client-role callers (F3.1.2).

## How it works

`app/main.py` exposes a catch-all `/api/{path}` proxy. It resolves the
upstream from the route table, (auth hook), strips client-supplied trusted
headers, forwards the request via `httpx`, and returns the upstream response.

## Route table

| Public prefix | Upstream service |
| ------------- | ---------------- |
| `/api/users` | user-service |
| `/api/suppliers` | supplier-service |
| `/api/orders` | order-service |
| `/api/credits` | credit-service |
| `/api/notifications` | notification-service |

## Run

```bash
make up
make test-api-gateway
```

Published on host port `${GATEWAY_PORT:-8080}` → container `8000`.
Exposes `GET /health`.

> Status: **scaffold**. Routing + unknown-route rejection + header stripping
> are implemented; token validation / RBAC enforcement are stubbed in
> `app/auth.py` for the team to complete.

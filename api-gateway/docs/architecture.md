# api-gateway Architecture

Internal architecture of **api-gateway** only. For how this service fits
among the others, see the repo-root `docs/architecture.md`;

## Style

Layered the same way as the domain services — `api/routes` (HTTP) →
`services` (business logic) — but with **no `repositories`/`models`
layer**: the gateway has no database of its own (per `AGENTS.md`), so there
is nothing to persist. Its only external dependency is the backend services
it proxies to, over HTTP.

## Components

| Component | File | Responsibility |
| --- | --- | --- |
| Proxy route | `app/api/routes/proxy.py` | The catch-all `/api/{path:path}` handler. HTTP-only: calls `GatewayService`, maps its domain exceptions to `ErrorEnvelope` JSON responses with the right status code. No routing/auth/forwarding logic lives here. |
| Health route | `app/api/routes/health.py` | `GET /health` liveness check. |
| Orchestrator | `app/services/gateway.py` (`GatewayService`) | The only component that sequences the three steps of handling one request: resolve the upstream, authorize the caller, forward the request. Owns the header-stripping rules on both the request and response side. |
| Auth | `app/services/auth.py` | `authenticate()` (JWT verify), `is_public()`, `build_trusted_headers()`. Delegates the actual public-route list and matching logic to `foc_shared.auth` (shared with user-service — see "Known failure mode" history in `flowchart.md`). |
| Routing | `app/services/routing.py` | `ROUTE_TABLE` (path prefix → backend base URL) and `resolve_upstream()`. Pure lookup, no I/O. |
| Exceptions | `app/services/exceptions.py` | `RouteNotFoundError`, `MissingBearerTokenError`, `InvalidTokenError` — routes catch these, never a raw `None`-check scattered across handlers. |
| Config | `app/config.py` | Env-driven settings: `jwt_secret`, backend service URLs. |

## Diagram

### Title: api-gateway internal layers and external boundaries

```mermaid
flowchart TD
    Client["Client / frontend"]

    subgraph API["app/api/routes"]
        Proxy["proxy.py<br/><i>catch-all /api/{path}</i>"]
        Health["health.py"]
    end

    subgraph SVC["app/services"]
        GW["gateway.py<br/><i>GatewayService — orchestrator</i>"]
        AUTH["auth.py<br/><i>authenticate, is_public,<br/>build_trusted_headers</i>"]
        ROUTE["routing.py<br/><i>ROUTE_TABLE, resolve_upstream</i>"]
        EXC["exceptions.py<br/><i>RouteNotFoundError,<br/>MissingBearerTokenError,<br/>InvalidTokenError</i>"]
    end

    Shared["foc_shared.auth<br/><i>PUBLIC_ROUTE_PREFIXES,<br/>is_public_route</i>"]
    Backends["Backend services<br/><i>user-, supplier-, order-,<br/>credit-, notification-service</i>"]

    Client -->|HTTP| Proxy
    Client -->|HTTP| Health
    Proxy --> GW
    GW --> AUTH
    GW --> ROUTE
    GW -.->|raises, caught by Proxy| EXC
    AUTH --> Shared
    GW -->|"HTTP<br/>+ X-User-Id / X-User-Role<br/>(Authorization stripped)"| Backends

    classDef sync fill:#e8f0fe,stroke:#4a6fa5,color:#1a1a1a;
    classDef shared fill:#f0e8fe,stroke:#7a4aa5,color:#1a1a1a;
    class Client,Proxy,Health,GW,AUTH,ROUTE,EXC,Backends sync;
    class Shared shared;
```

### Legend

| Symbol | Meaning |
| --- | --- |
| Rounded box (blue) | In-process, synchronous component within this service |
| Rounded box (purple) | External shared package (`foc_shared`), not owned by this service |
| Solid arrow | Direct function call |
| Dashed arrow | Exception raised by the callee, caught by the caller |

### Explained elements

- **`proxy.py` never touches routing, auth, or `httpx` directly.** It calls
  `GatewayService` and translates exactly three domain exceptions into HTTP
  responses (404, 401 ×2). This mirrors user-service's routes-only-translate
  convention — one place decides the status-code mapping, not one per
  handler.
- **`GatewayService.resolve()` runs before `.authorize()`.** An unknown
  route 404s regardless of whether a token was sent; a known-but-protected
  route only then checks auth. This ordering is deliberate and matches the
  original proxy's behavior — it must not be reordered casually, since it
  changes what an attacker probing for valid paths can infer from status
  codes.
- **`auth.py` doesn't own the public-route list.** `PUBLIC_ROUTE_PREFIXES`
  and the matching logic live in `foc_shared.auth`, imported by both this
  service and asserted against by user-service's own tests. This exists
  because the two once drifted out of sync silently (see
  `flowchart.md`) — this is the fix, not incidental sharing.
- **No repositories/models layer.** Nothing here is persisted; the gateway
  is stateless by design. The "external boundary" for this service is
  entirely outbound HTTP to backend services, not a database.
- **Response error shape is shared, not local.** `ErrorEnvelope` (`code`,
  `message`) comes from `foc_shared.errors` — the same contract every other
  service uses for its own error responses, so a client parses one shape
  everywhere.
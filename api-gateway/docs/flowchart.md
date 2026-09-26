# api-gateway Request Flow

Companion to `architecture.md`. Where the repo-root `docs/flowchart.md`
covers the login handshake and the OTP lifecycle (user-service's side), this
covers what happens **inside api-gateway** for every proxied request, now
grounded in the layered `services/` module split.

## 1. Full proxy request pipeline

### Title: GatewayService orchestration for one /api/{path} request

```mermaid
flowchart TD
    A["Incoming request<br/><i>app/api/routes/proxy.py</i>"]
    B["GatewayService.resolve(path)<br/><i>services/routing.py::resolve_upstream</i>"]
    C{"Upstream found?"}
    D["404 Not Found<br/><i>ErrorEnvelope-shaped JSON</i>"]
    E["GatewayService.authorize(path, request)<br/><i>services/auth.py</i>"]
    F{"is_public(path)?"}
    G["injected_headers = {}<br/><i>no token check</i>"]
    H{"Authorization: Bearer &lt;token&gt;<br/>present?"}
    I["401 — MissingBearerTokenError<br/><i>ErrorEnvelope-shaped JSON</i>"]
    J["authenticate(token)<br/><i>verify signature &amp; exp</i>"]
    K{"Token valid?"}
    L["401 — InvalidTokenError<br/><i>ErrorEnvelope-shaped JSON</i>"]
    M["build_trusted_headers(user_id, role)"]
    N["GatewayService.forward(...)<br/><i>strip client X-User-*/Authorization,<br/>inject trusted headers, httpx call</i>"]
    O{"Upstream request succeeds?"}
    P["502 Bad Gateway<br/><i>ErrorEnvelope-shaped JSON</i>"]
    Q["Return upstream response to client"]

    A --> B --> C
    C -- No --> D
    C -- Yes --> E
    E --> F
    F -- Yes --> G --> N
    F -- No --> H
    H -- No --> I
    H -- Yes --> J --> K
    K -- No --> L
    K -- Yes --> M --> N
    N --> O
    O -- No --> P
    O -- Yes --> Q

    classDef ok fill:#e8f0fe,stroke:#4a6fa5,color:#1a1a1a;
    classDef err fill:#fdeaea,stroke:#b3413e,color:#1a1a1a;
    class G,M,N,Q ok;
    class D,I,L,P err;
```

**Legend:** blue = handled successfully, request proceeds; red = rejected,
`proxy.py` returns immediately without calling `GatewayService.forward()`.

**Explained elements**

- **Route resolution happens before authorization**, both in the diagram and
  in `proxy.py`'s call order. `RouteNotFoundError` short-circuits before
  `GatewayService.authorize()` is even called — an invalid path 404s
  whether or not the caller sent a token.
- **`authenticate()` still never raises** — it returns `None` on any
  failure (missing/expired/malformed/bad signature), exactly as before the
  refactor. `GatewayService.authorize()` is the layer that turns that `None`
  into `InvalidTokenError`; `authenticate()` itself stays a pure,
  non-raising verifier so a bad token can never crash the proxy outright.
- **All four gateway exceptions are caught in exactly one place** —
  `app/api/routes/proxy.py` — and turned into ErrorEnvelope-shaped JSON with
  the matching status code. No handler duplicates that mapping.
- **Header stripping happens in `GatewayService.forward()`**, on both
  sides: client-supplied `Authorization` and `X-User-*` headers are
  stripped before forwarding (preventing role spoofing), and hop-by-hop
  response headers (`Content-Length`, `Transfer-Encoding`, `Connection`)
  are stripped before returning the upstream response to the client.

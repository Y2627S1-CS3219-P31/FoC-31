# Authentication & Request Flow

Companion to `architecture.md`, zoomed in on the api-gateway ↔ user-service
auth handshake and the per-request flow every other call goes through.

## 1. Login flow

### Title: Client login through the gateway to user-service

```mermaid
flowchart TD
    A["POST /api/users/login<br/><i>public route, via gateway</i>"]
    B["Proxy to user-service<br/><i>is_public() = true</i>"]
    C["Verify credentials<br/><i>against user-db</i>"]
    D{"Credentials valid?"}
    E["Return 401<br/><i>bad credentials</i>"]
    F["Issue JWT<br/><i>sub=user_id, role, exp</i>"]
    G["Return token to client"]

    A --> B --> C --> D
    D -- No --> E
    D -- Yes --> F --> G

    classDef ok fill:#e8f0fe,stroke:#4a6fa5,color:#1a1a1a;
    classDef err fill:#fdeaea,stroke:#b3413e,color:#1a1a1a;
    class F,G ok;
    class E err;
```

**Legend:** blue = handled by user-service on the happy path; red = rejected.

**Explained elements**

- The gateway does **no** credential checking here — `is_public()` matches
  `/api/users/login` and the request is proxied straight through
  (`api-gateway/app/auth.py`).
- user-service hashes-and-compares the password (`bcrypt`) and, only on
  success, issues a JWT (`app/services/security.py::issue_access_token`)
  with `sub`/`role`/`exp` claims — the exact shape the gateway later expects.
- Login fails closed for unverified or suspended accounts (see
  `app/services/user.py::authenticate`) even with a correct password.

## 2. Per-request auth flow (protected routes)

### Title: Gateway request pipeline grounded in api-gateway/app/{auth,main}.py

```mermaid
flowchart TD
    A["Incoming request"]
    B{"is_public(path)?"}
    BP["Bypass auth<br/><i>no token check</i>"]
    C["auth.authenticate(token)<br/><i>verify signature &amp; exp</i>"]
    D{"Token valid?"}
    E["Return 401<br/><i>unauthorized</i>"]
    F["build_trusted_headers()<br/><i>X-User-Id, X-User-Role</i>"]
    G["Strip client auth headers<br/><i>prevent role spoofing</i>"]
    H["resolve_upstream() proxy"]
    I["Backend service checks role<br/><i>using X-User-Role header</i>"]
    J["Return response to client"]

    A --> B
    B -- Yes --> BP --> H
    B -- No --> C --> D
    D -- No --> E
    D -- Yes --> F --> G --> H --> I --> J

    classDef ok fill:#e8f0fe,stroke:#4a6fa5,color:#1a1a1a;
    classDef err fill:#fdeaea,stroke:#b3413e,color:#1a1a1a;
    class F,G,H,J ok;
    class E err;
```

**Legend:** blue = handled by the gateway (or downstream, once forwarded);
red = rejected at the gateway.

**Explained elements**

- The gateway never re-derives a role decision per route today —
  `routing.py`'s `ROUTE_TABLE` is a plain path-prefix map with no role
  metadata. It authenticates and injects identity; **RBAC enforcement for a
  specific action happens inside the backend service**, using the trusted
  `X-User-Role` header.
- `authenticate()` never raises on a bad token — it returns `None`, and the
  proxy in `main.py` turns that into a 401. A malformed/expired JWT can't
  crash the gateway.
- `Authorization` is stripped before forwarding, same as any client-supplied
  `X-User-*` header — backends must not see the raw token or be able to
  spoof identity via headers.

> **Known failure mode (hit this once already):** `is_public(path)` in
> `api-gateway/app/auth.py` matches by exact string against
> `PUBLIC_PREFIXES`. That list is currently:
> `/health`, `/api/users/register`, `/api/users/login`,
> `/api/users/otp/verify`, `/api/users/otp/resend`. If user-service's route
> paths ever change (they were renamed once already, from `/verify-otp` /
> `/resend-otp` to `/otp/verify` / `/otp/resend`), the gateway's allowlist
> does **not** update itself — it silently starts requiring a JWT for a
> route the caller has no token for yet, breaking registration/verification
> with no obvious error on the user-service side (its own tests still pass,
> since they bypass the gateway entirely). Whoever renames a user-service
> auth-adjacent route must update `PUBLIC_PREFIXES` in the same PR.

## 3. OTP lifecycle (register → resend → verify)

### Title: Email-verification OTP handling in user-service

```mermaid
flowchart TD
    A["POST /api/users/register"]
    B{"Email already<br/>registered?"}
    C{"Existing account<br/>email_verified?"}
    D["409 Conflict<br/><i>already registered</i>"]
    E["Refresh password_hash /<br/>display_name on existing row"]
    F["Create new User row<br/><i>email_verified = false</i>"]
    G["Issue OTP (purpose=EMAIL_VERIFICATION)<br/><i>5-min expiry, hashed code</i>"]
    H["POST /api/users/otp/resend"]
    I{"Account found &amp;<br/>not yet verified?"}
    J["200 generic response"]
    K["POST /api/users/otp/verify"]
    L{"Latest unconsumed OTP:<br/>correct &amp; unexpired?"}
    M["400 Bad Request"]
    N["mark_consumed(otp_id)<br/><i>atomic UPDATE ... WHERE consumed_at IS NULL</i>"]
    O{"Row actually<br/>updated?"}
    P["400 — already used<br/><i>closes race between concurrent verifies</i>"]
    Q["email_verified = true<br/>enqueue UserRegistered outbox event"]

    A --> B
    B -- Yes --> C
    B -- No --> F
    C -- Yes --> D
    C -- No --> E --> G
    F --> G

    H --> I
    I -- No --> J
    I -- Yes --> G

    K --> L
    L -- No --> M
    L -- Yes --> N --> O
    O -- No --> P
    O -- Yes --> Q

    classDef ok fill:#e8f0fe,stroke:#4a6fa5,color:#1a1a1a;
    classDef err fill:#fdeaea,stroke:#b3413e,color:#1a1a1a;
    class E,F,G,N,Q ok;
    class D,M,P err;
```

**Explained elements**

- Re-registering an email that exists but was never verified does **not**
  409 — it refreshes that row's password/display name and issues a new OTP.
  This is intentional (see prior discussion): someone who lost the first
  code, or mistyped their password, isn't permanently locked out of their
  own `@u.nus.edu` address.
- Resending an OTP always returns the same `200` response for an unknown,
  verified, or unverified address. A code is sent only for an existing,
  unverified account, preventing email enumeration.
- Verification only ever checks the **latest** unconsumed OTP for that user
  (`OtpRepository.get_latest_unconsumed`, ordered by `created_at`), so an
  older code from a previous register/resend simply fails the hash
  comparison — no separate invalidation step is needed.
- `mark_consumed` is a single `UPDATE ... WHERE consumed_at IS NULL`, and
  `verify_email` checks its row-count. This closes a real race: two
  concurrent `verify-otp` requests with the same valid code can no longer
  both succeed — only the one that wins the atomic update proceeds to set
  `email_verified = true` and enqueue `UserRegistered`; the other gets
  "code already used."
- `OtpCode.purpose` (`OtpPurpose.EMAIL_VERIFICATION` today,
  `PASSWORD_RESET` reserved) means the same table and repository can back a
  future forgot-password flow without a schema change.

## 4. First-admin bootstrap

On startup, the lifespan hook creates the schema and checks
`BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD`. If both are present,
the service validates them with `CreateAdminRequest` and calls
`UserService.ensure_bootstrap_admin()`. The operation is idempotent: an
existing admin is returned unchanged, an existing non-admin with that email
fails startup, and PostgreSQL advisory locking prevents duplicate creation
when multiple instances start together. The password is never reset on later
starts.

### Title: First-admin bootstrap on startup (`seed_bootstrap_admin`)

<!-- AI-influenced: diagram drafted with OpenCode (Claude Opus); see ai/usage-log.md -->

```mermaid
flowchart TD
    A["App startup (lifespan)<br/><i>init_db() then seed_bootstrap_admin()</i>"]
    B{"BOOTSTRAP_ADMIN_EMAIL<br/>and _PASSWORD both set?"}
    S["Skip — no bootstrap<br/><i>normal start</i>"]
    V["Validate as CreateAdminRequest<br/><i>@u.nus.edu, password rules</i>"]
    L["Take PG advisory xact lock<br/><i>serialize concurrent instances</i>"]
    E{"Account with<br/>that email exists?"}
    R{"Existing role<br/>== admin?"}
    K["Return existing admin unchanged<br/><i>password never reset</i>"]
    F["Fail startup<br/><i>RuntimeError: email belongs to non-admin</i>"]
    C["Create admin<br/><i>email_verified = true, hashed password</i>"]

    A --> B
    B -- No --> S
    B -- Yes --> V --> L --> E
    E -- Yes --> R
    R -- Yes --> K
    R -- No --> F
    E -- No --> C

    classDef ok fill:#e8f0fe,stroke:#4a6fa5,color:#1a1a1a;
    classDef err fill:#fdeaea,stroke:#b3413e,color:#1a1a1a;
    class S,V,L,K,C ok;
    class F err;
```

**Legend:** blue = normal/idempotent outcome; red = startup aborts.

**Explained elements**

- Bootstrap only runs when **both** credentials are configured; otherwise the
  service starts normally with no seeded admin (`app/bootstrap.py`).
- The **PostgreSQL advisory transaction lock**
  (`pg_advisory_xact_lock`) serializes multiple app instances starting at once
  so they cannot each create the same admin; the unique-email constraint is the
  fallback for other databases and concurrent callers
  (`app/services/user.py::ensure_bootstrap_admin`).
- The operation is **idempotent**: an already-existing admin is returned
  unchanged (the password is never reset on later starts). An existing account
  with that email that is **not** an admin aborts startup, surfacing the
  misconfiguration instead of silently escalating a normal user.

## 5. Registration → initial credit allocation (async)

### Title: register → verify → outbox → RabbitMQ → credit-service

<!-- AI-influenced: diagram drafted with OpenCode (Claude Opus); see ai/usage-log.md -->

This spans two services and the broker. The `UserRegistered` publish path is
**implemented** (transactional outbox + background relay), so it is drawn with
solid delivery arrows; only the downstream credit ledger write belongs to
credit-service.

```mermaid
sequenceDiagram
    autonumber
    actor U as Client
    participant US as user-service
    participant DB as user-db
    participant OW as outbox_worker<br/>(user-service)
    participant MQ as RabbitMQ<br/>foc.user.events (fanout)
    participant CR as credit-service

    U->>US: POST /api/users/register
    US->>US: generate 6-digit OTP, hash (SHA-256)
    US->>DB: INSERT user (email_verified=false) + OtpCode (hashed)

    alt OTP_DEV_MODE and no SMTP
        US-->>US: log "OTP_DEV_MODE active: verification code for ... is ..."
    else SMTP configured
        US-->>U: email OTP
    end

    U->>US: POST /api/users/otp/verify (code)
    Note over US,DB: single transaction
    US->>DB: set email_verified=true + INSERT event_outbox(UserRegistered)
    US-->>U: 200 verified

    loop every 5s
        OW->>DB: SELECT outbox WHERE published_at IS NULL
        OW->>MQ: publish UserRegistered (payload: user_id, email, timestamp)
        OW->>DB: set published_at (or record last_error and retry)
    end

    MQ-->>CR: deliver UserRegistered (fanout)
    CR->>CR: allocate INITIAL_CREDIT_ALLOCATION to new account
```

**Legend:** solid `->>` = a call/publish that happens; dashed `-->>` = a
delivery/response; `loop` = the periodic relay; `alt` = OTP delivery channel.

**Explained elements**

- **Atomic verify + enqueue.** `verify_email()` sets `email_verified = true`
  and inserts the `UserRegistered` outbox row in the **same** transaction
  (`app/services/events.py::enqueue_user_registered`), so a user is never marked
  verified without a pending event, nor vice-versa.
- **The relay is real, not planned.** `outbox_worker` runs from the app lifespan
  (`app/main.py`), polling every 5 seconds; `dispatch_outbox_once` publishes any
  row with `published_at IS NULL` to the `foc.user.events` **fanout** exchange
  and stamps `published_at`, or records `last_error` and retries. A broker
  outage therefore delays, but never loses, the event.
- **credit-service is the consumer.** It binds a durable queue to the
  `foc.user.events` fanout exchange and, on `UserRegistered`, provisions the
  initial balance of `INITIAL_CREDIT_ALLOCATION`
  (`credit-service/app/services/consumer.py`); redeliveries are handled
  idempotently.
- **Dev-mode OTP.** With `OTP_DEV_MODE=true` and no SMTP host, the code is
  written to the user-service log instead of emailed
  (`app/services/notification.py`) — this is what the D2 demo reads. It must
  never be enabled in a real deployment.

## 6. Role change (promote / demote) with guards

### Title: `PATCH /api/users/admin/{id}/role` guard flow (`set_role`)

<!-- AI-influenced: diagram drafted with OpenCode (Claude Opus); see ai/usage-log.md -->

The role-change endpoint exists (`app/api/routes/users.py::update_user_role` →
`app/services/user.py::set_role`), so its guards are diagrammed here.

```mermaid
flowchart TD
    A["PATCH /api/users/admin/{id}/role<br/><i>admin only (_require_admin)</i>"]
    B{"target == actor<br/>and new role != admin?"}
    C["400 — cannot demote self"]
    D{"target user exists?"}
    E["404 — user not found"]
    F{"new role == current role?"}
    G["200 — no-op, unchanged"]
    H{"demoting an admin?<br/>(admin -> client)"}
    I{"remaining non-suspended<br/>admins <= 1?"}
    J["400 — cannot demote last admin"]
    K["Set role, commit<br/>200 updated user"]

    A --> B
    B -- Yes --> C
    B -- No --> D
    D -- No --> E
    D -- Yes --> F
    F -- Yes --> G
    F -- No --> H
    H -- No --> K
    H -- Yes --> I
    I -- Yes --> J
    I -- No --> K

    classDef ok fill:#e8f0fe,stroke:#4a6fa5,color:#1a1a1a;
    classDef err fill:#fdeaea,stroke:#b3413e,color:#1a1a1a;
    class G,K ok;
    class C,E,J err;
```

**Legend:** blue = success/no-op; red = rejected.

**Explained elements**

- **Self-demotion is blocked (400).** An admin cannot demote itself
  (`user_id == actor_id and new_role != admin`), preventing an admin from
  accidentally removing its own access mid-session.
- **Last-admin protection (400).** Demoting an `admin` to `client` is refused
  when only one non-suspended admin would remain, so the system can never be
  left with zero active administrators (`count_admins(exclude_suspended=True)`).
- **No-op returns unchanged (200).** Setting the same role the user already has
  short-circuits to a 200 with the user unchanged — the guards above apply only
  to actual demotions.
- **Admin-only + 404.** The route is gated by `_require_admin` (401 without
  identity, 403 for a non-admin), and an unknown target id is a 404.

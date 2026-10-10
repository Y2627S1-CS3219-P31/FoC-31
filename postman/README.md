<!-- AI-influenced: authored with OpenCode (Claude Opus); see ai/usage-log.md. -->

# FoC D2 Demo — Postman collection

Demonstrates Milestone **D2** (User Service + Supplier Service) end-to-end
through the **API Gateway** (`http://localhost:8080`), with no UI. Every request
asserts its expected status code (and key body fields) and chains tokens/ids
through environment variables so the folders run in order.

- `FoC-D2.postman_collection.json` — the collection (Postman schema v2.1).
- `FoC-local.postman_environment.json` — local environment variables.
- The curl + jq twin of this flow is [`../scripts/demo.sh`](../scripts/demo.sh)
  (numbered blocks 01–07 match the folders one-to-one).

## Per-service reference collections

Alongside the end-to-end D2 demo, `collections/` holds standalone per-service
API collections (Postman git-sync format: one `.request.yaml` per endpoint):

| Collection | Covers |
| ---------- | ------ |
| `FoC User Service API` | Auth (login → token), registration + OTP, profile (`/me`), admin user-management. |
| `FoC Supplier Service API` | Supplier discovery + admin CRUD (create/update/deactivate/reactivate). |
| `FoC Credit Service API` | Balance, transaction history, reservation lifecycle (reserve/amend/transfer/release). |

> `order-service` and `notification-service` are not covered yet — their routes
> are `501 Not Implemented` stubs.

All three go through the gateway (`{​{baseUrl}}/api/...`) and use the same
**FoC local (D2 demo)** environment.

### Getting a bearer token (do this first)

Every protected request authenticates with a JWT bearer token. Each collection
starts with a **Login admin** request (`POST /api/users/login`) that asserts
`token_type: "bearer"` and saves the returned `access_token` into the
`adminToken` environment variable; subsequent admin requests send
`Authorization: Bearer {​{adminToken}}`. The User Service collection also has a
**Login client** request that populates `clientToken` for client-scoped calls
(requires a registered+verified client — run its registration/OTP folder first).

Because auth is enforced at the gateway (which strips client-supplied
`X-User-*` headers and re-injects the real role from the JWT), these collections
use bearer tokens rather than raw `X-User-Role` headers.

## Collection structure (run top to bottom)

| Folder | Demonstrates |
| ------ | ------------ |
| `00 Health` | Gateway liveness. |
| `01 Registration (User)` | Register client → verify OTP → resend; non-NUS 422; duplicate 409. |
| `02 Authentication` | Admin/client login (saves tokens), wrong password 401, `/me`, gateway 401s. |
| `03 RBAC evidence` | Client blocked from admin ops (403); spoofed `X-User-Role` stripped by gateway. |
| `04 Supplier queries (as client)` | List/paginate/filter/search; empty→200 total 0; get-by-id; unknown→404; bad `page_size`→422. |
| `05 Supplier CRUD (as admin)` | Create/patch/deactivate/reactivate + validation (422) and conflict (409). |
| `06 Profile (as client)` | Self-update; privilege fields rejected (422); bad contact 422. |
| `07 User administration (as admin)` | List/suspend/unsuspend, create admin, role change + guards. |

## Prerequisites (bring the stack up)

The collection talks to a running local stack. From the repo root:

```bash
cp .env.example .env            # if you don't already have one
# In .env set (dev only):
#   OTP_DEV_MODE=true
#   BOOTSTRAP_ADMIN_EMAIL=e0000000@u.nus.edu
#   BOOTSTRAP_ADMIN_PASSWORD=admin1234
#   BOOTSTRAP_ADMIN_DISPLAY_NAME=System Administrator

docker compose up --build -d
# wait until healthy:
curl -s http://localhost:8080/health      # -> {"status":"ok"}
```

> The environment file ships with `adminEmail=e0000000@u.nus.edu` /
> `adminPassword=admin1234` to match the local `.env` bootstrap admin. These are
> **local dev placeholders, not real secrets**. If your `.env` uses different
> `BOOTSTRAP_ADMIN_*` values, update `adminEmail`/`adminPassword` in the
> environment (or pass `--env-var` to newman) to match.

## Import into the Postman app

1. **Import** → drop both JSON files in.
2. Select the **FoC local (D2 demo)** environment (top-right).
3. Run the folders in order (00 → 07). `clientEmail` is generated automatically
   on the first request of folder 01; tokens and ids are saved as you go.

## The manual OTP step

`01 Registration` verifies a real OTP. With `OTP_DEV_MODE=true` (and no SMTP
configured) the user-service **logs** the code instead of emailing it:

```
docker compose logs user-service | grep "verification code for"
# OTP_DEV_MODE active: verification code for demo...@u.nus.edu is 123456 (dev-only; ...)
```

Copy the 6-digit code into the `otpCode` environment variable, then send
**Verify OTP**.

### View OTP emails locally (Mailpit)

Alternatively, the stack ships a **Mailpit** container (a fake SMTP server that
captures outgoing mail). With the `.env` configured for it
(`SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_STARTTLS=false`,
`OTP_DEV_MODE=false`), the user-service *emails* the code instead of logging it:

```
docker compose up -d mailpit user-service
# register a user, then open the Mailpit web UI:
open http://localhost:8025          # the OTP email appears here
```

Read the 6-digit code from the captured email, set `otpCode`, then send
**Verify OTP**. No real email leaves your machine and no mail credentials are
needed.

## Running with newman

Install ad-hoc via `npx` (no global install needed):

### Mode (a) — interactive (full flow incl. OTP)

Run folder `01` on its own, read the code from the log, set `otpCode`, then run
the rest. newman can't pause for the manual code, so split the run:

```bash
# 1) Register + generate clientEmail (stores it in a shared env export)
npx newman run FoC-D2.postman_collection.json \
  -e FoC-local.postman_environment.json \
  --folder "01 Registration (User)" \
  --export-environment /tmp/foc-env.json
# (this run's OTP-verify step will fail until you supply the code — that's expected)

# 2) Read the OTP from the log
docker compose logs user-service | grep "verification code for" | tail -1

# 3) Continue, supplying the code and reusing the generated clientEmail
npx newman run FoC-D2.postman_collection.json \
  -e /tmp/foc-env.json \
  --env-var otpCode=<the-6-digits> \
  --folder "01 Registration (User)" \
  --folder "02 Authentication" --folder "03 RBAC evidence" \
  --folder "04 Supplier queries (as client)" \
  --folder "05 Supplier CRUD (as admin)" \
  --folder "06 Profile (as client)" \
  --folder "07 User administration (as admin)"
```

### Mode (b) — CI-ish (skip OTP, use a pre-verified client)

Pre-create and verify a client with the shell script (which auto-reads the
dev-mode OTP), then run folders `02`–`07` against that verified `clientEmail`:

```bash
# Creates + verifies a client, prints its email at the end:
NO_PAUSE=1 ./../scripts/demo.sh            # or run from repo root: ./scripts/demo.sh

npx newman run FoC-D2.postman_collection.json \
  -e FoC-local.postman_environment.json \
  --folder "00 Health" \
  --folder "02 Authentication" --folder "03 RBAC evidence" \
  --folder "04 Supplier queries (as client)" \
  --folder "05 Supplier CRUD (as admin)" \
  --folder "06 Profile (as client)" \
  --folder "07 User administration (as admin)" \
  --env-var clientEmail=<verified-client-email>
```

Because `01 Registration` is skipped, folder `02` logs in the already-verified
`clientEmail` passed via `--env-var`.

> **Use a *fresh* verified client for each mode-(b) run.** Folder `07` promotes
> the client to admin (`Promote client -> admin`), so re-running the whole
> collection against the *same* `clientEmail` would then see an admin where it
> expects a client (breaking the RBAC/suspend assertions). Generate a new
> verified client (e.g. run `demo.sh` again, or register+verify a new email)
> before each clean end-to-end mode-(b) run.

## Notes on assertions

- `role` is asserted **lowercase** (`"client"` / `"admin"`) because that is how
  the user-service serializes the `Role` enum value. (The user-service
  `docs/api-contract.md` shows uppercase `CLIENT`/`ADMIN`; the code is the
  source of truth — see the AI usage log / final summary.)
- Supplier bodies/responses are **camelCase** (`pageSize`, `startingTime`,
  `locationDescription`); user bodies/responses are **snake_case**
  (`display_name`, `contact_number`, `is_suspended`).

# frontend

Responsive **React + TypeScript + Vite** single-page app for FoC, built with
the **Mantine** UI library. It talks only to the **API Gateway**
(`VITE_API_BASE_URL`) and is responsive across desktop and mobile viewports
(project M1).

For D2 the SPA implements the authentication flow and the supplier-management
experience (browse + admin CRUD) plus an admin portal.

## Pages

| Route | Access | Purpose |
| ----- | ------ | ------- |
| `/login` | public | Email + password login (JWT) |
| `/register` | public | Create a `@u.nus.edu` account |
| `/verify-otp` | public | Verify email with the OTP code |
| `/suppliers` | authenticated | Browse suppliers: search, category/zone filter, sort, pagination |
| `/suppliers/:id` | authenticated | Supplier detail; admins get edit/manage |
| `/profile` | authenticated | View role/email (read-only) + edit name/contact |
| `/admin/suppliers` | admin | Supplier CRUD: table + create/edit form + deactivate |
| `/admin/clients` | admin | Client accounts: search/filter, suspend/reinstate, create admin |

Client-side role checks are **UX only**; the gateway + services enforce
authorization (RBAC is the server's responsibility).

## Config

`VITE_API_BASE_URL` (see root `.env.example`) points the app at the gateway
(default `http://localhost:8080`). The typed client lives in `src/lib/api.ts`;
auth state in `src/lib/auth.tsx`.

## Run

```bash
# via the whole stack
make up            # served at http://localhost:5173

# or locally
cd frontend && npm install && npm run dev
```

### Demo accounts / OTP

- The first admin is created on user-service startup from the
  `BOOTSTRAP_ADMIN_*` env vars.
- Registration requires email OTP verification. With no SMTP configured, set
  `OTP_DEV_MODE=true` (see root `.env.example`) — the verification code is then
  written to the **user-service logs** (`docker compose logs user-service`)
  instead of emailed. Never enable this in a real deployment.

## Test

End-to-end regression tests use **Playwright** (`playwright.config.ts`). The
specs mock the API Gateway with Playwright routes, so **no backend, database, or
`.env` is required** — Playwright starts the Vite dev server on
`http://localhost:5173` for you.

```bash
cd frontend

# one-time setup
npm install
npx playwright install          # download Chromium, Firefox and WebKit

# auth regression suite (login, register, OTP, session + route guards)
npx playwright test tests/auth

# everything under tests/
npx playwright test
```

Useful variants:

```bash
npx playwright test tests/auth --project=chromium   # one browser
npx playwright test tests/auth/login.spec.ts        # one file
npx playwright test tests/auth --headed             # watch it run
npx playwright test tests/auth --ui                 # interactive UI mode
npx playwright show-report                          # open the HTML report
```

If a dev server is already running on port 5173 it is reused; only CI always
starts a fresh one.

## Build

```bash
cd frontend && npm run build   # tsc typecheck + vite production build
```

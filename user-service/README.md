# user-service

Manages user **registration, authentication, RBAC, and profile** — and a
user's ability to act as both a **requester** and a **courier** (backlog:
User Service; project M2).

## Responsibilities (from backlog)

- **F1 Registration** — `@u.nus.edu` email + password, OTP email verification,
  uniqueness, password strength; provision initial credits on success (F1.3).
- **F2 Login / session** — issue time-limited session credential (JWT),
  logout (invalidate), forgotten-password reset.
- **F3 Profile** — view/update editable fields (display name, contact number);
  credit balance retrieved from the Credit Service, not stored locally.
- **F4 Roles** — `admin` and `client` (client = requester + courier).
- **F5 Admin** — list / suspend / reinstate client accounts.
- Publishes `UserRegistered` so the Credit Service can create the account.

## Layout

```text
app/
├── main.py            # FastAPI app + router wiring
├── config.py          # env-driven settings
├── db.py              # async SQLAlchemy engine/session + Base
├── api/routes/        # health, users (stubs)
├── models/            # ORM models (stub)
├── schemas/           # Pydantic DTOs (stub)
├── services/          # business logic (stub)
└── repositories/      # persistence access (stub)
tests/                 # pytest smoke tests
```

## Run

```bash
# via the whole stack
make up

# or just this service's tests
make test-user-service
```

Database: `user-db` (PostgreSQL). Exposes `GET /health`.

> Status: **scaffold**. Endpoints return `501 Not Implemented` until built.

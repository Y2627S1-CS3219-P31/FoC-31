# User Service API Contract

This contract describes the user-service HTTP API and its gateway-facing paths.

## Route prefixes

| Access path | Prefix |
| --- | --- |
| Direct user-service request | `/users` |
| API gateway request | `/api/users` |

The API gateway removes `/api` before forwarding the request to user-service.

## Shared validation rules

- `email` must be a valid `@u.nus.edu` address.
- `password` must contain at least 8 characters, including letters and digits.
- `display_name` must contain 1–50 characters.
- `contact_number` must match `^[89]\d{7}$` when provided.
- Unknown request fields are rejected with `422 Unprocessable Entity`.

## Public endpoints

### Register

```http
POST /users/register
```

Gateway path: `POST /api/users/register`

Request body:

```json
{
  "email": "alice@u.nus.edu",
  "password": "correct-horse1",
  "display_name": "Alice",
  "contact_number": "91234567"
}
```

`contact_number` is optional.

Success response — `201 Created`:

```json
{
  "id": "user-id",
  "email": "alice@u.nus.edu",
  "message": "Registered. Check your email for a verification code."
}
```

Possible errors: `409` email already registered, `422` invalid body, `429` registration/OTP rate limit, `503` email delivery failure.

### Verify email OTP

```http
POST /users/otp/verify
```

Gateway path: `POST /api/users/otp/verify`

Request body:

```json
{
  "email": "alice@u.nus.edu",
  "code": "123456"
}
```

Success response — `200 OK`:

```json
{
  "verified": true,
  "message": "email verified"
}
```

Possible errors: `400` invalid, expired, consumed, or locked OTP; `422` invalid body.

### Resend email OTP

```http
POST /users/otp/resend
```

Gateway path: `POST /api/users/otp/resend`

Request body:

```json
{
  "email": "alice@u.nus.edu"
}
```

Success response — `200 OK`:

```json
{
  "message": "Verification code sent. Check your email."
}
```

The same response is returned for unknown or already verified accounts to prevent email enumeration.

Possible errors: `422` invalid body, `429` resend cooldown, `503` email delivery failure.

### Login

```http
POST /users/login
```

Gateway path: `POST /api/users/login`

Request body:

```json
{
  "email": "alice@u.nus.edu",
  "password": "correct-horse1"
}
```

Success response — `200 OK`:

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer",
  "expires_in": 3600
}
```

Possible errors: `401` invalid credentials, `403` suspended or unverified account, `422` invalid body, `503` authentication configuration failure.

## Authenticated endpoints

Protected requests receive these trusted headers from the API gateway:

```http
X-User-Id: user-id
X-User-Role: CLIENT
```

### Get current profile

```http
GET /users/me
```

Gateway path: `GET /api/users/me`

Success response — `200 OK`:

```json
{
  "id": "user-id",
  "email": "alice@u.nus.edu",
  "display_name": "Alice",
  "contact_number": "91234567",
  "role": "CLIENT",
  "email_verified": true
}
```

Possible errors: `401` missing identity header, `404` user not found.

### Update current profile

```http
PATCH /users/me
```

Gateway path: `PATCH /api/users/me`

Request body:

```json
{
  "display_name": "Alice Tan",
  "contact_number": "81234567"
}
```

At least one field is required; both fields are optional individually.

Success response — `200 OK`:

```json
{
  "id": "user-id",
  "email": "alice@u.nus.edu",
  "display_name": "Alice Tan",
  "contact_number": "81234567",
  "role": "CLIENT",
  "email_verified": true
}
```

Possible errors: `401` missing identity header, `404` user not found, `422` invalid body.

## Administrator endpoints

Administrator requests require:

```http
X-User-Id: admin-user-id
X-User-Role: ADMIN
```

### Create administrator

```http
POST /users/admin
```

Gateway path: `POST /api/users/admin`

Request body:

```json
{
  "email": "admin@u.nus.edu",
  "password": "strong-admin1",
  "display_name": "System Admin",
  "contact_number": "91234567"
}
```

Success response — `201 Created`:

```json
{
  "id": "admin-id",
  "email": "admin@u.nus.edu",
  "display_name": "System Admin",
  "contact_number": "91234567",
  "role": "ADMIN",
  "email_verified": true,
  "is_suspended": false,
  "created_at": "2026-09-26T09:00:00"
}
```

Possible errors: `401` missing identity, `403` non-admin identity, `409` email already registered, `422` invalid body.

### List users

```http
GET /users/admin?limit=50&offset=0
```

Gateway path: `GET /api/users/admin?limit=50&offset=0`

Success response — `200 OK`:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

`limit` must be between 1 and 100; `offset` must not be negative.

Possible errors: `401` missing identity, `403` non-admin identity, `422` invalid query parameters.

### Suspend user

```http
POST /users/admin/{user_id}/suspend
```

Gateway path: `POST /api/users/admin/{user_id}/suspend`

Request body: none.

Success response: the updated `AdminUserResponse` payload from the create-admin endpoint with `is_suspended: true`.

Possible errors: `400` self-suspension or administrator target, `401` missing identity, `403` non-admin identity, `404` user not found.

### Unsuspend user

```http
POST /users/admin/{user_id}/unsuspend
```

Gateway path: `POST /api/users/admin/{user_id}/unsuspend`

Request body: none.

Success response: the updated `AdminUserResponse` payload with `is_suspended: false`.

Possible errors: `400` administrator target, `401` missing identity, `403` non-admin identity, `404` user not found.

## Health endpoint

```http
GET /health
```

Success response — `200 OK`:

```json
{
  "status": "ok"
}
```

## Common status codes

| Status | Meaning |
| --- | --- |
| `200` | Request successful |
| `201` | Resource created |
| `400` | Invalid OTP or admin operation |
| `401` | Missing or invalid identity |
| `403` | Insufficient permissions |
| `404` | User not found |
| `409` | Email already registered |
| `422` | Invalid request data |
| `429` | Rate limit exceeded |
| `503` | External service unavailable |

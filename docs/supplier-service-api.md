<!-- AI-influenced: drafted with OpenCode (Claude Sonnet); see ai/usage-log.md. this file only formalizes the decisions that the team made. -->

# Supplier Service — API Specification

Contract that the supplier-service exposes to its consumers (the frontend via
the API Gateway, and other backend services). This is the **human-readable**
reference; the machine-readable companion is
[`supplier-service-openapi.yaml`](./supplier-service-openapi.yaml). The two are
kept in sync — endpoint set, field names, enums, and error codes are identical.

> Status: **implemented** — list, detail, create, update, and deactivate are
> served by the supplier-service. The contract is stable so consumers can
> integrate against a fixed shape (backlog N5.1).

---

## 1. Overview

- **Public base URL** (through the gateway): `/api/suppliers`
- **Internal base URL** (service-to-service, on the Docker network):
  `http://supplier-service:8000/api/suppliers`
- **Media type:** `application/json` (UTF-8)
- **Live schema:** each FastAPI service also serves its auto-generated spec at
  `/openapi.json` and interactive docs at `/docs`. This file is the curated,
  reviewed contract; the auto-generated one reflects whatever is implemented.

The API Gateway is the **only** public entry point. It strips any
client-supplied identity headers, authenticates the caller, and injects the
trusted headers below before proxying `/api/suppliers/*` to the service
(`ROUTE_TABLE` in `api-gateway/app/routing.py`). Backend services are never
exposed to clients directly.

---

## 2. Conventions

### HTTP semantics

| Method  | Use                                                                     |
| ------- | ----------------------------------------------------------------------- |
| `GET`   | Read a resource or a collection. Safe + idempotent.                     |
| `POST`  | Create a resource, or invoke a state-changing action (e.g. deactivate). |
| `PATCH` | Partially update an existing resource.                                  |

### Status codes

| Code                       | Meaning in this service                                                      |
| -------------------------- | ---------------------------------------------------------------------------- |
| `200 OK`                   | Successful read or update.                                                   |
| `201 Created`              | Supplier created.                                                            |
| `400 Bad Request`          | Malformed request (e.g. invalid query param).                                |
| `401 Unauthorized`         | Missing/invalid authentication (enforced at the gateway).                    |
| `403 Forbidden`            | Authenticated but not permitted (e.g. client hitting an admin route).        |
| `404 Not Found`            | Supplier ID does not exist (F3.2).                                           |
| `409 Conflict`             | State conflict (e.g. deactivating an already-deactivated supplier).          |
| `422 Unprocessable Entity` | Validation error (missing mandatory field, category not in the allowed set). |
| `501 Not Implemented`      | Scaffold placeholder — remove once implemented.                              |

### Error format

All error responses use the shared **error envelope**
(`foc_shared.errors.ErrorEnvelope`):

```json
{
  "code": "not_found",
  "message": "Supplier 'sup_123' was not found."
}
```

`code` is a stable, machine-readable string (see §7); `message` is a
human-readable explanation (F3.2.1). Authorization failures are distinguishable
from authentication failures and do not reveal whether a resource exists
(system-wide N4.1).

---

## 3. Authentication & Authorization

The service trusts only the gateway-injected headers
(`foc_shared.auth`) — it must never accept a client-asserted role:

| Header        | Meaning                             |
| ------------- | ----------------------------------- |
| `X-User-Id`   | Authenticated caller's user id.     |
| `X-User-Role` | Caller's role: `admin` or `client`. |

### Access matrix

| Operation                      | Roles allowed     | Notes                                       |
| ------------------------------ | ----------------- | ------------------------------------------- |
| Discovery (`GET /suppliers`)   | `admin`, `client` | Public catalog reads (F2).                  |
| Detail (`GET /suppliers/{id}`) | `admin`, `client` | (F3).                                       |
| Create / Update / Deactivate   | `admin` only      | Management operations (F1). Client → `403`. |
| Service lookup / validation    | trusted services  | Consumed by Order Service (F5).             |

RBAC is also enforced at the edge by the gateway, but the service performs its
own check (defence in depth; backlog N4).

---

## 4. Data model

### `Supplier`

| Field                 | Type              | Notes                                                    |
| --------------------- | ----------------- | -------------------------------------------------------- |
| `id`                  | string            | Server-assigned identifier.                              |
| `name`                | string            | Mandatory (F1.1.1).                                      |
| `category`            | `Category` (enum) | Mandatory; constrained to a predefined set (F1.1.2).     |
| `building`            | string            | Mandatory; campus building/location (F1.1.1). Maps from the seed `Building` column. |
| `floor`               | string \| null    | From seed data.                                          |
| `locationDescription` | string \| null    | Free-text hint (e.g. "Next to NUS Co-op").               |
| `latitude`            | number \| null    | Decimal degrees, `-90`–`90`.                             |
| `longitude`           | number \| null    | Decimal degrees, `-180`–`180`.                           |
| `startingTime`        | string \| null    | Opening time, 24-hour `HH:MM` (e.g. `09:00`).            |
| `closingTime`         | string \| null    | Closing time, 24-hour `HH:MM` (e.g. `18:00`).            |
| `imageUrl`            | string \| null    | Optional image reference.                                |
| `active`              | boolean           | `true` = active, `false` = deactivated (F3.1.1).         |

### `Category` (enum)

Derived from the seed dataset (`data/csv/supplier-seed-data.csv`). The
authoritative set is owned by the team; current values:

```
Food · Food/Coffee · Shopping · Printing
```

These four values are the canonical set (they match the seed dataset's `Type`
column exactly). The same validation applies on create and update (F1.2.1);
a `category` outside this set is rejected with `422 validation_error`.

---

## 5. Endpoints

### 5.1 `GET /suppliers` — list / filter / search

List **active** suppliers. Supports filtering, keyword search, and pagination.

- **Auth:** `admin`, `client`
- **Query parameters:**

  | Param       | Type                | Default | Description                                                  |
  | ----------- | ------------------- | ------- | ------------------------------------------------------------ |
  | `category`  | string (repeatable) | —       | Filter by one or more categories (F2.1.1).                   |
  | `zone`      | string              | —       | Filter by campus zone/location (F2.1.2).                     |
  | `q`         | string              | —       | Case-insensitive keyword search over name + location (F2.2). |
  | `page`      | integer ≥ 1         | `1`     | Page number (F5.1.2).                                        |
  | `page_size` | integer 1–100       | `20`    | Items per page (F5.1.2).                                     |

- **200 response:**

  ```json
  {
    "items": [
      {
        "id": "sup_001",
        "name": "Anna's x Soup Union",
        "category": "Food",
        "building": "Central Library",
        "active": true
      }
    ],
    "page": 1,
    "pageSize": 20,
    "total": 1
  }
  ```

- **Notes:** Deactivated suppliers are excluded from discovery results
  (F1.4). Returns an empty `items` array (not `404`) when nothing matches
  (F1.4.1, F2.2.3).

### 5.2 `GET /suppliers/{id}` — detail

Return the full details of a single supplier by id.

- **Auth:** `admin`, `client`
- **Path params:** `id` — supplier identifier.
- **200 response:** a full `Supplier` object, including `active` status (F3.1.1).
- **404 response:** error envelope with an explanatory message (F3.2, F3.2.1):

  ```json
  { "code": "not_found", "message": "Supplier 'sup_999' was not found." }
  ```

### 5.3 `POST /suppliers` — create

Create a new supplier record.

- **Auth:** `admin` only (F1.1) — `client` → `403`.
- **Request body (`SupplierCreate`):**

  ```json
  {
    "name": "Cool Spot",
    "category": "Food",
    "building": "Com2",
    "floor": "1",
    "locationDescription": "Opp LT16",
    "latitude": 1.2940156,
    "longitude": 103.7738478,
    "startingTime": "09:00",
    "closingTime": "21:30",
    "imageUrl": null
  }
  ```

- **201 response:** the created `Supplier` (with `id`, `active: true`).
- **422:** missing/empty mandatory field (`name`, `category`, `building`),
  `category` outside the allowed set, `latitude`/`longitude` out of range
  (`-90`–`90` / `-180`–`180`), or `startingTime`/`closingTime` not in `HH:MM`
  format (F1.1.1, F1.1.2).

### 5.4 `PATCH /suppliers/{id}` — update

Update the `name`, `category`, or `building` (and other editable fields)
of an existing supplier (F1.2).

- **Auth:** `admin` only.
- **Request body (`SupplierUpdate`):** any subset of editable fields.
- **200 response:** the updated `Supplier`.
- **422:** `category` update fails the same validation as create (F1.2.1).
- **404:** unknown id.

### 5.5 `POST /suppliers/{id}/deactivate` — deactivate

Deactivate a supplier (soft delete). The record remains retrievable (F1.3.1),
is excluded from active discovery (F1.4), but is preserved for historical
orders (system-wide N4).

- **Auth:** `admin` only (F1.3).
- **200 response:** the `Supplier` with `active: false`.
- **409:** already deactivated.
- **404:** unknown id.

> Downstream effect (planned, Sprint 3): deactivation is intended to trigger
> the order-cancellation cascade. The supplier-service is synchronous-only
> today; the event mechanism is documented in
> [`event-catalog.md`](./event-catalog.md) and owned by the Order Service.

### 5.6 Service lookup — validate supplier by id

Exposes supplier data for other services to retrieve/validate a supplier by id,
returning the current active/deactivated status (F5.1, F5.1.1). Consumed by the
**Order Service** before creating an order (it rejects orders against a
deactivated supplier — Order F1.1.6).

- **Auth:** trusted services (via the gateway/internal network).
- Reuses the public read shape: service-to-service callers hit
  `GET /api/suppliers/{id}` on the Docker network (no separate internal
  endpoint). `GET /api/suppliers` supports pagination for list/search (F5.1.2).

---

## 6. Pagination, filtering & sorting

- **Pagination:** `page` (1-based) + `page_size` on list/search responses; the
  envelope returns `page`, `pageSize`, and `total` (F5.1.2).
- **Filtering:** `category` (repeatable) and `zone` combine (AND) with `q`.
- **Empty results:** an empty `items` array with `total: 0` — never a `404`
  (F1.4.1, F2.2.3).

---

## 7. Error codes

| `code`             | HTTP | When                                               |
| ------------------ | ---- | -------------------------------------------------- |
| `validation_error` | 422  | Missing mandatory field or invalid `category`.     |
| `bad_request`      | 400  | Malformed query/path parameter.                    |
| `unauthorized`     | 401  | Missing/invalid authentication (from the gateway). |
| `forbidden`        | 403  | Role not permitted for the operation.              |
| `not_found`        | 404  | Supplier id does not exist.                        |
| `conflict`         | 409  | State conflict (e.g. re-deactivating).             |

---

## 8. Versioning & stability

- Breaking changes to this contract are **versioned** rather than silently
  altered (backlog N5.2). Approach (team to confirm): version prefix on the
  public path (e.g. `/api/v1/suppliers`) or a version header.
- Request/response schemas and error codes are documented here and in the
  OpenAPI file so consumers can integrate independently (N5.1, N5.1.1).

---

## 9. Related documents

- [`supplier-service-openapi.yaml`](./supplier-service-openapi.yaml) — machine-readable OpenAPI 3.1 spec.
- [`architecture.md`](./architecture.md) — supplier-service component diagram.
- [`event-catalog.md`](./event-catalog.md) — async order-lifecycle events.

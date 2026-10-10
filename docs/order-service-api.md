<!-- AI-influenced: updated with Codex; see ai/usage-log.md. This file documents the implemented Order Service contract; endpoint and architecture decisions remain team-owned. -->

# Order Service — API Specification

Contract that the order-service exposes to its consumers (the frontend through
the API Gateway, and other backend services). This is the **human-readable**
reference for the implemented Sprint 1 endpoints. The running FastAPI service
provides the machine-readable OpenAPI document.

> Status: `POST /orders`, `GET /orders`, `GET /orders/{order_id}`, and
> `DELETE /orders/{order_id}` are **implemented**. Supplier validation, credit
> reservation, and credit release are part of the implemented workflows.
> Order acceptance, later lifecycle transitions, event publishing, and expiry
> processing remain planned.

---

## 1. Overview

- **Configured public prefix** (through the gateway): `/api/orders`
- **Internal base URL** (service-to-service, on the Docker network):
  `http://order-service:8000/orders`
- **Media type:** `application/json` (UTF-8)
- **Live schema:** `/openapi.json`
- **Interactive documentation:** `/docs`

The API Gateway is intended to be the only public entry point. It must remove
client-supplied identity headers, authenticate the caller, and inject trusted
identity headers before forwarding the request to the service.

> Integration status: the gateway route table contains `/api/orders`, but its
> current proxy forwards that prefix unchanged while this service exposes
> `/orders`. Authentication and trusted-header injection are also scaffolded.
> The gateway must rewrite the path and complete authentication before the
> configured public prefix is operational.

---

## 2. Conventions

### HTTP semantics

| Method   | Use                                                        |
| -------- | ---------------------------------------------------------- |
| `GET`    | Read an order or the collection of available orders.       |
| `POST`   | Create an order.                                           |
| `DELETE` | Permanently delete an eligible requester-owned order.       |

### Status codes

| Code                        | Meaning in this service                                                     |
| --------------------------- | --------------------------------------------------------------------------- |
| `200 OK`                    | Successful order read or available-order listing.                           |
| `201 Created`               | Order created after supplier validation and credit reservation.             |
| `204 No Content`            | Order deleted; the response body is empty.                                  |
| `401 Unauthorized`          | Authentication failed at the API Gateway.                                   |
| `403 Forbidden`             | The caller does not own the requested order.                                |
| `404 Not Found`             | An order, supplier, or requester credit account does not exist.             |
| `409 Conflict`              | The order state or a credit reservation prevents the operation.             |
| `422 Unprocessable Entity`  | A required header or request-body value failed validation.                  |
| `500 Internal Server Error` | An Order Service database operation or unexpected operation failed.         |
| `502 Bad Gateway`           | A dependency returned an invalid, unexpected, or unusable response.         |
| `503 Service Unavailable`   | Supplier Service or Credit Service is temporarily unavailable.              |

### Error format

Order Service errors use the shared **error envelope**
(`foc_shared.errors.ErrorEnvelope`):

```json
{
  "code": "order_not_found",
  "message": "Order '123e4567-e89b-12d3-a456-426614174000' was not found."
}
```

`code` is a stable, machine-readable string (see §7); `message` is a
human-readable explanation. Request validation failures are also converted to
this envelope with `code: "validation_error"`.

---

## 3. Authentication & Authorization

The service trusts only gateway-injected identity headers from
`foc_shared.auth`. Clients must not be allowed to assert these headers through
the public gateway.

| Header        | Required by these routes | Meaning                                   |
| ------------- | ------------------------ | ----------------------------------------- |
| `X-User-Id`   | Yes                      | Authenticated caller's user identifier.   |
| `X-User-Role` | No                       | Gateway contract field; currently unused. |

### Access matrix

| Operation                       | Current authorization rule                                  |
| ------------------------------- | ----------------------------------------------------------- |
| Create an order                 | Any caller with a trusted `X-User-Id`.                      |
| List available orders           | Any caller with a trusted `X-User-Id`; own orders excluded. |
| Read an order by ID             | Only the order's requester.                                 |
| Delete an order by ID           | Only the requester, subject to state and assignment rules.  |

The service does not currently enforce a role using `X-User-Role`. A missing
`X-User-Id` at the service boundary produces a `422 validation_error`; public
authentication failures are the gateway's responsibility.

---

## 4. Data model

### `OrderResponse`

| Field               | Type           | Notes                                                          |
| ------------------- | -------------- | -------------------------------------------------------------- |
| `order_id`          | string         | Server-generated UUID string and primary key.                   |
| `name`              | string         | Required; stripped and non-empty on creation.                   |
| `details`           | string         | Required; stripped and non-empty on creation.                   |
| `reward`            | integer        | Required and greater than zero.                                 |
| `deadline`          | date-time      | Timezone-aware ISO 8601 value; must be in the future on create. |
| `supplier_id`       | string         | Required; supplier must exist and be active.                    |
| `requester_id`      | string         | Taken from `X-User-Id`, never from the request body.            |
| `courier_id`        | string \| null | Assigned courier; `null` for a newly created order.             |
| `pickup_location`   | string         | Required, stripped, and non-empty.                              |
| `delivery_location` | string         | Required, stripped, and non-empty.                              |
| `status`            | `OrderStatus`  | Server-managed lifecycle state; initially `OPEN`.               |
| `created_at`        | date-time      | Database-generated creation timestamp.                          |

The persisted order also stores an internal `reservation_id` for releasing
the Credit Service reservation. That field is not exposed by `OrderResponse`.

### `OrderStatus` (enum)

```text
OPEN · ACCEPTED · PICKED_UP · AWAITING_APPROVAL
COMPLETED · CANCELLED · EXPIRED
```

The implemented endpoints create `OPEN` orders, list open and unassigned
orders, and allow hard deletion only while an order is still open and
unassigned. Routes for the other lifecycle transitions are not implemented.

### `OrderCreate`

The request body contains only client-provided fields:

```json
{
  "name": "Collect lunch",
  "details": "One vegetarian rice bowl",
  "reward": 5,
  "deadline": "2026-10-05T15:00:00+08:00",
  "supplier_id": "sup_001",
  "pickup_location": "The Deck",
  "delivery_location": "COM3"
}
```

---

## 5. Endpoints

### 5.1 `POST /orders` — create an order **(implemented)**

Create an `OPEN` order owned by the authenticated requester.

- **Auth:** trusted `X-User-Id` header required.
- **Request body:** `OrderCreate` (see §4).
- **Workflow:**

  1. Retrieve the supplier through Supplier Service and require `active: true`.
  2. Generate the order UUID.
  3. Reserve `reward` credits through Credit Service for that order UUID.
  4. Insert the order and reservation ID in an Order Service database
     transaction.
  5. If database insertion fails, request release of the credit reservation
     before returning a persistence error.

- **201 response:** the persisted `OrderResponse`.

  ```json
  {
    "order_id": "123e4567-e89b-12d3-a456-426614174000",
    "name": "Collect lunch",
    "details": "One vegetarian rice bowl",
    "reward": 5,
    "deadline": "2026-10-05T15:00:00+08:00",
    "supplier_id": "sup_001",
    "requester_id": "user-123",
    "courier_id": null,
    "pickup_location": "The Deck",
    "delivery_location": "COM3",
    "status": "OPEN",
    "created_at": "2026-10-04T13:00:00+08:00"
  }
  ```

- **422 response:** a required field is absent; a string field is empty;
  `reward` is not positive; or `deadline` lacks a timezone or is not in the
  future.
- **Dependency and persistence errors:**

  | HTTP | `code`                           | When                                               |
  | ---- | -------------------------------- | -------------------------------------------------- |
  | 404  | `supplier_not_found`             | Supplier Service reports an unknown supplier.      |
  | 409  | `supplier_inactive`              | The selected supplier is inactive.                 |
  | 404  | `credit_account_not_found`       | The requester has no Credit Service account.       |
  | 409  | `insufficient_credits`           | The requester cannot reserve the reward amount.    |
  | 409  | `reservation_conflict`           | Credit Service reports a reservation conflict.     |
  | 500  | `order_persistence_failed`       | The order could not be inserted.                    |
  | 502  | `dependency_invalid_response`    | A dependency violated its response contract.       |
  | 502  | `dependency_unexpected_response` | A dependency returned an unmapped response.         |
  | 503  | `dependency_unavailable`         | Supplier or Credit Service is unavailable.          |

### 5.2 `GET /orders` — list available orders **(implemented)**

Return orders available to the authenticated caller for courier discovery.

- **Auth:** trusted `X-User-Id` header required.
- **Query parameters:** none.
- **Filters applied:**

  - `status` is `OPEN`;
  - `courier_id` is `null`; and
  - `requester_id` differs from the caller's `X-User-Id`.

- **Ordering:** `deadline` ascending, then `order_id` ascending.
- **200 response:** a JSON array of `OrderResponse` objects.

  ```json
  [
    {
      "order_id": "123e4567-e89b-12d3-a456-426614174000",
      "name": "Collect lunch",
      "details": "One vegetarian rice bowl",
      "reward": 5,
      "deadline": "2026-10-05T15:00:00+08:00",
      "supplier_id": "sup_001",
      "requester_id": "user-123",
      "courier_id": null,
      "pickup_location": "The Deck",
      "delivery_location": "COM3",
      "status": "OPEN",
      "created_at": "2026-10-04T13:00:00+08:00"
    }
  ]
  ```

- **Empty result:** returns `[]`, not `404`.
- **Pagination:** not implemented.
- **500 response:** `order_retrieval_failed` when the database query fails.
- **Current limitation:** no deadline predicate is applied. An overdue order
  remains visible while its persisted status is still `OPEN`.

### 5.3 `GET /orders/{order_id}` — requester order detail **(implemented)**

Return one order only when it belongs to the authenticated requester.

- **Auth:** trusted `X-User-Id` header required; caller must own the order.
- **Path parameter:** `order_id` — server-generated UUID string.
- **200 response:** the complete `OrderResponse`.
- **403 response:** the order belongs to another requester.

  ```json
  {
    "code": "order_access_denied",
    "message": "You do not have permission to access order '123e4567-e89b-12d3-a456-426614174000'."
  }
  ```

- **404 response:** no order has the supplied ID.

  ```json
  {
    "code": "order_not_found",
    "message": "Order '123e4567-e89b-12d3-a456-426614174000' was not found."
  }
  ```

- **500 response:** `order_retrieval_failed` when the database lookup fails.

The implementation does not provide courier or administrator detail access.

### 5.4 `DELETE /orders/{order_id}` — delete an order **(implemented)**

Permanently delete an order after releasing its reserved credits.

- **Auth:** trusted `X-User-Id` header required; caller must own the order.
- **Path parameter:** `order_id` — server-generated UUID string.
- **Deletion workflow:**

  1. Lock the order row for update.
  2. Require the caller to be the order's `requester_id`.
  3. Require `status: OPEN` and `courier_id: null`.
  4. Release the stored credit reservation through Credit Service.
  5. Hard-delete the row and commit the database transaction.

- **204 response:** successful deletion with no response body.
- **Expected errors:**

  | HTTP | `code`                             | When                                              |
  | ---- | ---------------------------------- | ------------------------------------------------- |
  | 403  | `order_access_denied`              | The order belongs to another requester.           |
  | 404  | `order_not_found`                  | No order has the supplied ID.                     |
  | 409  | `invalid_order_state`              | The order is assigned or not `OPEN`.               |
  | 409  | `reservation_conflict`             | Credit Service rejects the release as a conflict. |
  | 500  | `order_deletion_failed`            | The database deletion fails.                      |
  | 502  | `credit_reservation_not_found`     | Credit Service cannot find the reservation.       |
  | 502  | `credit_reservation_access_denied` | Credit Service rejects reservation ownership.     |
  | 502  | `dependency_invalid_response`      | Credit Service violates its response contract.    |
  | 502  | `dependency_unexpected_response`   | Credit Service returns an unmapped response.       |
  | 503  | `dependency_unavailable`           | Credit Service is unavailable.                    |

The implementation hard-deletes the row; it does not retain a `CANCELLED`
record or publish a cancellation event. Credit release is performed while the
database transaction is open, but the two services do not share a distributed
transaction.

---

## 6. Filtering, sorting & pagination

- `GET /orders` accepts no query parameters.
- Availability filtering uses order status, courier assignment, and requester
  ownership. It does not currently filter by deadline.
- Results are sorted by `deadline` ascending and then `order_id` ascending.
- Pagination is not implemented; the response is a bare JSON array.

---

## 7. Error codes

| `code`                             | HTTP | When                                                    |
| ---------------------------------- | ---- | ------------------------------------------------------- |
| `validation_error`                 | 422  | Header or request-body validation fails.                |
| `order_not_found`                  | 404  | The order ID does not exist.                            |
| `order_access_denied`              | 403  | The caller does not own the requested order.            |
| `invalid_order_state`              | 409  | Deletion is invalid for the order state or assignment.  |
| `supplier_not_found`               | 404  | Supplier Service reports an unknown supplier.           |
| `supplier_inactive`                | 409  | The selected supplier is inactive.                      |
| `credit_account_not_found`         | 404  | The requester has no credit account.                    |
| `insufficient_credits`             | 409  | The requester cannot reserve the reward.                |
| `reservation_conflict`             | 409  | Credit reservation creation or release conflicts.       |
| `credit_reservation_not_found`     | 502  | The stored reservation cannot be found.                 |
| `credit_reservation_access_denied` | 502  | Credit Service rejects access to the reservation.       |
| `order_persistence_failed`         | 500  | Database insertion fails.                               |
| `order_retrieval_failed`           | 500  | Database retrieval fails.                               |
| `order_deletion_failed`            | 500  | Database deletion fails.                                |
| `dependency_invalid_response`      | 502  | A dependency violates its response contract.            |
| `dependency_unexpected_response`   | 502  | A dependency returns an unmapped response.              |
| `dependency_unavailable`           | 503  | A required dependency is unavailable.                   |
| `internal_error`                   | 500  | An unexpected unhandled error occurs.                   |

---

## 8. Versioning & stability

- Breaking contract changes should be versioned rather than silently changing
  existing consumers. The team has not selected a path or header strategy.
- The generated OpenAPI document reflects the running code. This curated
  document additionally explains authorization, dependency workflows, and
  current implementation limitations.
- Planned lifecycle endpoints must be added only after the team agrees their
  paths and schemas and the routes are implemented.

---

## 9. Related documents

- [`order-state-machine.jpg`](./order-state-machine.jpg) — Order lifecycle diagram.
- [`event-catalog.md`](./event-catalog.md) — planned asynchronous lifecycle events.
- [`architecture.md`](./architecture.md) — repository architecture overview.
- [`../order-service/README.md`](../order-service/README.md) — service responsibilities and run instructions.

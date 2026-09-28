<!-- AI-influenced: drafted with Codex; see ai/usage-log.md. This file documents the team-provided Order Service contract and the current implementation. -->

# Order Service - API Specification

Contract that the order-service exposes to its consumers through the API
Gateway. This is the human-readable reference for the Sprint 1 endpoint set.
The FastAPI-generated OpenAPI document remains the machine-readable record of
the routes that are currently implemented.

> Status: `POST /orders`, `GET /orders`, `GET /orders/{order_id}`, and
> `DELETE /orders/{order_id}` are implemented. Supplier validation, credit
> reservation, lifecycle actions after creation, event publishing, and expiry
> processing are planned but are not part of this implemented slice.

---

## 1. Overview

- **Public base URL specified by the team:** `/api/order`
- **Internal base URL** (on the Docker network):
  `http://order-service:8000/orders`
- **Media type:** `application/json` (UTF-8)
- **Live schema:** the Order Service serves its generated OpenAPI document at
  `/openapi.json` and interactive documentation at `/docs`.

The endpoint paths in this document are the paths exposed by the Order Service
itself. The API Gateway is expected to translate the public base URL to the
internal `/orders` path. Gateway routing and authentication are owned by the
API Gateway and must be aligned separately; this document does not claim that
the current gateway scaffold already implements that mapping.

---

## 2. Conventions

### HTTP semantics

| Method   | Use                                                        |
| -------- | ---------------------------------------------------------- |
| `GET`    | Read an order or the collection of available orders.       |
| `POST`   | Create a new order.                                        |
| `DELETE` | Delete an order when ownership and lifecycle rules permit. |

### Status codes

| Code                       | Meaning in this service                                      |
| -------------------------- | ------------------------------------------------------------ |
| `200 OK`                   | Successful order read or available-order listing.            |
| `201 Created`              | Order created successfully.                                  |
| `204 No Content`           | Order deleted successfully; the response body is empty.      |
| `401 Unauthorized`         | Missing or invalid authentication at the API Gateway.        |
| `403 Forbidden`            | The authenticated requester does not own the order.          |
| `404 Not Found`            | The order ID does not exist.                                 |
| `409 Conflict`             | The order cannot be deleted in its current lifecycle state.  |
| `422 Unprocessable Entity` | Missing header, malformed path value, or invalid request body. |

### Error format

Application errors returned explicitly by the Order Service use the shared
error envelope (`foc_shared.errors.ErrorEnvelope`):

```json
{
  "code": "not_found",
  "message": "Order '123' was not found."
}
```

`code` is machine-readable and `message` explains the error. Request and
header validation failures currently use FastAPI's standard `422` validation
response instead of this envelope.

---

## 3. Authentication and authorization

The service expects the trusted identity header defined in
`foc_shared.auth`:

| Header        | Required | Meaning                                  |
| ------------- | -------- | ---------------------------------------- |
| `X-User-Id`   | Yes      | Authenticated caller's user identifier.  |
| `X-User-Role` | No       | Gateway contract field; these routes do not currently read it. |

In the intended deployment, clients do not set these headers themselves. The
API Gateway authenticates the caller, removes client-supplied identity
headers, and injects trusted values. The Order Service trusts the resulting
`X-User-Id` value.

### Access matrix

| Operation                     | Current authorization rule                                  |
| ----------------------------- | ----------------------------------------------------------- |
| Create an order               | Any caller with a trusted `X-User-Id`.                      |
| List available orders         | Any caller with a trusted `X-User-Id`; own orders excluded. |
| Read an order by ID           | Only the order's requester.                                 |
| Delete an order by ID         | Only the requester, subject to lifecycle rules.             |

The current routes do not enforce a role using `X-User-Role`.

---

## 4. Data model

### `Order`

| Field               | Type               | Notes                                                        |
| ------------------- | ------------------ | ------------------------------------------------------------ |
| `id`                | integer            | Server-assigned, auto-incrementing primary key.               |
| `name`              | string             | Required; whitespace is stripped and the value cannot be empty. |
| `details`           | string             | Required; whitespace is stripped and the value cannot be empty. |
| `reward`            | integer            | Required and greater than zero.                               |
| `deadline`          | date-time          | Required ISO 8601 value with a timezone; must be in the future. |
| `supplier_id`       | string             | Required and non-empty. Active-supplier validation is planned. |
| `pickup_location`   | string             | Required and non-empty.                                      |
| `delivery_location` | string             | Required and non-empty.                                      |
| `requester_id`      | string             | Taken from `X-User-Id`; clients do not provide it in the body. |
| `courier_id`        | string or `null`   | Assigned courier; `null` when the order is available.         |
| `status`            | `OrderStatus`      | Server-managed lifecycle state; initially `OPEN`.             |

### `OrderStatus`

The lifecycle module defines these states:

```text
OPEN
ACCEPTED
PICKED_UP
AWAITING_APPROVAL
COMPLETED
CANCELLED
EXPIRED
```

The implemented Sprint 1 endpoints create `OPEN` orders, discover available
`OPEN` orders, and validate deletion against the lifecycle rules. Endpoints
that perform the other transitions are not implemented yet.

### Request and response schemas

`OrderCreate` contains only client-provided fields:

```json
{
  "name": "Collect lunch",
  "details": "One vegetarian rice bowl",
  "reward": 5,
  "deadline": "2026-09-26T15:00:00+08:00",
  "supplier_id": "sup_001",
  "pickup_location": "The Deck",
  "delivery_location": "COM3"
}
```

`OrderResponse` adds the server-managed fields `id`, `requester_id`,
`courier_id`, and `status`.

---

## 5. Endpoints

### 5.1 `POST /orders` - create an order **(implemented)**

Create a new order owned by the authenticated requester.

- **Auth:** trusted `X-User-Id` header required.
- **Request body:** `OrderCreate`.

  ```json
  {
    "name": "Collect lunch",
    "details": "One vegetarian rice bowl",
    "reward": 5,
    "deadline": "2026-09-26T15:00:00+08:00",
    "supplier_id": "sup_001",
    "pickup_location": "The Deck",
    "delivery_location": "COM3"
  }
  ```

- **201 response:** the persisted `OrderResponse`.

  ```json
  {
    "id": 1,
    "name": "Collect lunch",
    "details": "One vegetarian rice bowl",
    "reward": 5,
    "deadline": "2026-09-26T15:00:00+08:00",
    "supplier_id": "sup_001",
    "pickup_location": "The Deck",
    "delivery_location": "COM3",
    "requester_id": "user-123",
    "courier_id": null,
    "status": "OPEN"
  }
  ```

- **422:** a required field is absent; a string field is empty; `reward` is
  not positive; or `deadline` lacks a timezone or is not in the future.
- **Current behavior:** the requester ID comes from the header and the order
  is written directly to the Order Service database with status `OPEN`.
- **Planned behavior:** validate that the supplier exists and is active, and
  reserve the reward through the Credit Service before the order becomes
  `OPEN`. Those cross-service checks are not currently implemented.

### 5.2 `GET /orders` - list available orders **(implemented)**

Return orders available to the authenticated caller for courier discovery.

- **Auth:** trusted `X-User-Id` header required.
- **Query parameters:** none in the current Sprint 1 implementation.
- **Filters applied:**

  - `status` is `OPEN`;
  - `courier_id` is `null`;
  - `deadline` is later than the current UTC time; and
  - `requester_id` differs from the caller's `X-User-Id`.

- **Ordering:** earliest deadline first, with `id` ascending as a stable
  tie-breaker.
- **200 response:** a JSON array of `OrderResponse` objects.

  ```json
  [
    {
      "id": 1,
      "name": "Collect lunch",
      "details": "One vegetarian rice bowl",
      "reward": 5,
      "deadline": "2026-09-26T15:00:00+08:00",
      "supplier_id": "sup_001",
      "pickup_location": "The Deck",
      "delivery_location": "COM3",
      "requester_id": "user-123",
      "courier_id": null,
      "status": "OPEN"
    }
  ]
  ```

- **Empty result:** returns `[]`, not `404`.
- **Pagination:** not implemented.

### 5.3 `GET /orders/{order_id}` - requester order detail **(implemented)**

Return one order only when it belongs to the authenticated requester.

- **Auth:** trusted `X-User-Id` header required; caller must own the order.
- **Path parameter:** `order_id` - integer order identifier.
- **200 response:** the complete `OrderResponse`.
- **403 response:** the order exists but belongs to another requester.

  ```json
  {
    "code": "forbidden",
    "message": "You do not have permission to access order '1'."
  }
  ```

- **404 response:** no order has the supplied ID.

  ```json
  {
    "code": "not_found",
    "message": "Order '999' was not found."
  }
  ```

This endpoint is for a requester retrieving their own order. The current
implementation does not provide courier or administrator detail access.

### 5.4 `DELETE /orders/{order_id}` - delete an order **(implemented)**

Delete an order when the authenticated requester owns it and the lifecycle
rules permit cancellation.

- **Auth:** trusted `X-User-Id` header required; caller must own the order.
- **Path parameter:** `order_id` - integer order identifier.
- **Deletion conditions:**

  - the caller is the order's `requester_id`;
  - `courier_id` is `null`; and
  - a transition from the current state to `CANCELLED` is permitted by the
    lifecycle state machine.

- **204 response:** successful deletion with no response body.
- **403 response:** the order belongs to another requester.
- **404 response:** no order has the supplied ID.
- **409 response:** a courier is assigned or the current status cannot
  transition to `CANCELLED`.

  ```json
  {
    "code": "invalid_order_state",
    "message": "An order with an assigned courier cannot be deleted."
  }
  ```

The normal deletable state is `OPEN` with no assigned courier. The current
implementation permanently deletes the row after validating the transition;
it does not retain the row with status `CANCELLED`.

---

## 6. Filtering, sorting, and pagination

- `GET /orders` accepts no query parameters in the current implementation.
- Availability filtering is performed by the service using status, courier
  assignment, deadline, and requester ownership.
- Results are sorted by `deadline` ascending and then `id` ascending.
- Pagination is not implemented; the response is a bare JSON array.

---

## 7. Error codes

| `code`                | HTTP | When                                                   |
| --------------------- | ---- | ------------------------------------------------------ |
| `unauthorized`        | 401  | Authentication fails at the API Gateway.               |
| `forbidden`           | 403  | The caller does not own the requested order.           |
| `not_found`           | 404  | The order ID does not exist.                           |
| `invalid_order_state` | 409  | Deletion is not valid for the order's assignment/state. |

FastAPI-generated `422` responses do not currently use one of the stable
application error codes above.

---

## 8. Versioning and stability

- Breaking changes to the public contract should be versioned rather than
  silently changing existing clients. The team has not yet selected a version
  prefix or header strategy.
- The generated OpenAPI document reflects the running code. This curated
  document explains authorization, filtering, state rules, and planned gaps.
- Planned lifecycle endpoints must be added here when their paths and request
  and response schemas are agreed and implemented.

---

## 9. Related documents

- [`order-state-machine.jpg`](./order-state-machine.jpg) - Order lifecycle diagram.
- [`event-catalog.md`](./event-catalog.md) - planned asynchronous lifecycle events.
- [`architecture.md`](./architecture.md) - repository architecture overview.
- [`../order-service/README.md`](../order-service/README.md) - Order Service responsibilities and run instructions.

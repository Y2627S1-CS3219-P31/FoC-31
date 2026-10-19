"""Which backend routes the API gateway exposes to browsers.

This is the only file to edit when a service adds or removes a client-facing
endpoint. The matching logic lives in ``app/services/routing.py``.

Default deny: the gateway forwards ONLY the (method, path) pairs below. Any
other request, including a listed path with the wrong method, gets ``404`` and
never reaches a backend. A new backend route stays private until someone
deliberately adds it here.

To expose a route:
1. Add ``("METHOD", "/api/<service>/...")`` under its service. A ``{name}``
   segment matches exactly one path segment (an id), e.g. ``{order_id}``.
   Do not add routes that only other services should call.
2. Add the same entry to ``tests/public_api_surface.json`` (run the gateway
   tests; the failure message shows the expected list).
3. If the route must work without a login, also add it to
   ``PUBLIC_ROUTE_PREFIXES`` in ``shared/foc_shared/auth.py``.

Changes to this file need a review from its code owner (``.github/CODEOWNERS``).
"""

from __future__ import annotations

from app.config import settings

ROUTE_TABLE: dict[str, str] = {
    "/api/users": settings.user_service_url,
    "/api/suppliers": settings.supplier_service_url,
    "/api/orders": settings.order_service_url,
    "/api/credits": settings.credit_service_url,
    "/api/notifications": settings.notification_service_url,
}


EXPOSED_ROUTES: tuple[tuple[str, str], ...] = (
    # user-service
    ("POST", "/api/users/register"),
    ("POST", "/api/users/otp/verify"),
    ("POST", "/api/users/otp/resend"),
    ("POST", "/api/users/login"),
    ("GET", "/api/users/me"),
    ("PATCH", "/api/users/me"),
    ("GET", "/api/users/admin"),
    ("POST", "/api/users/admin"),
    ("POST", "/api/users/admin/{user_id}/suspend"),
    ("POST", "/api/users/admin/{user_id}/unsuspend"),
    ("PATCH", "/api/users/admin/{user_id}/role"),

    # supplier-service
    ("GET", "/api/suppliers"),
    ("POST", "/api/suppliers"),
    ("GET", "/api/suppliers/{supplier_id}"),
    ("PATCH", "/api/suppliers/{supplier_id}"),
    ("POST", "/api/suppliers/{supplier_id}/deactivate"),
    ("POST", "/api/suppliers/{supplier_id}/reactivate"),

    # order-service
    ("GET", "/api/orders"),
    ("POST", "/api/orders"),
    ("GET", "/api/orders/{order_id}"),
    ("DELETE", "/api/orders/{order_id}"),

    # credit-service (read-only for clients)
    ("GET", "/api/credits/{user_id}/balance"),
    ("GET", "/api/credits/{user_id}/transactions"),

    # notification-service
    ("GET", "/api/notifications/{user_id}"),
)

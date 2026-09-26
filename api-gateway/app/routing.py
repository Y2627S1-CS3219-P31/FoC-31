from __future__ import annotations

from app.config import settings

ROUTE_TABLE: dict[str, str] = {
    "/api/users": settings.user_service_url,
    "/api/suppliers": settings.supplier_service_url,
    "/api/orders": settings.order_service_url,
    "/api/credits": settings.credit_service_url,
    "/api/notifications": settings.notification_service_url,
}


def resolve_upstream(path: str) -> str | None:
    for prefix, base_url in ROUTE_TABLE.items():
        if path == prefix or path.startswith(prefix + "/"):
            return base_url
    return None

# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from app.config import settings

ROUTE_TABLE: dict[str, str] = {
    "/api/users": settings.user_service_url,
    "/api/suppliers": settings.supplier_service_url,
    "/api/order": settings.order_service_url,
    "/api/credits": settings.credit_service_url,
    "/api/notifications": settings.notification_service_url,
}


def resolve_upstream(path: str) -> str | None:
    for prefix, base_url in ROUTE_TABLE.items():
        if path == prefix or path.startswith(prefix + "/"):
            return base_url
    return None


def resolve_upstream_path(path: str) -> str:
    if path == "/api/order" or path.startswith("/api/order/"):
        return "/orders" + path[len("/api/order") :]
    return path

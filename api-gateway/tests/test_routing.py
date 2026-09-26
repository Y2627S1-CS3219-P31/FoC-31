# AI-influenced: implemented with Codex; see ai/usage-log.md.
from app.config import settings
from app.routing import resolve_upstream, resolve_upstream_path


def test_order_create_public_path_maps_to_internal_orders_collection() -> None:
    assert resolve_upstream("/api/order") == settings.order_service_url
    assert resolve_upstream_path("/api/order") == "/orders"

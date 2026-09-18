from __future__ import annotations

from foc_shared.events import OrderEvent


async def publish_order_event(event: OrderEvent) -> None:
    raise NotImplementedError

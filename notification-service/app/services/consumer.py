from __future__ import annotations

from foc_shared.events import OrderEvent


async def handle_order_event(event: OrderEvent) -> None:
    raise NotImplementedError

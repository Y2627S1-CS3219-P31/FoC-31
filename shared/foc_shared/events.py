from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class OrderEventType(str, Enum):
    ORDER_ACCEPTED = "OrderAccepted"
    ORDER_PICKED_UP = "OrderPickedUp"
    ORDER_DELIVERED = "OrderDelivered"
    ORDER_COMPLETED = "OrderCompleted"
    ORDER_CANCELLED = "OrderCancelled"
    COURIER_WITHDRAWN = "CourierWithdrawn"
    ORDER_EXPIRED = "OrderExpired"


class OrderEvent(BaseModel):
    event_type: OrderEventType
    order_id: str
    requester_id: str
    courier_id: str | None = None
    timestamp: datetime
    reason: str | None = None

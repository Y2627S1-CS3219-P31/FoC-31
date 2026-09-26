from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


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

class UserRegisteredEvent(BaseModel):
    event_type: str = "UserRegistered"
    user_id: str
    email: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
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


# AI-influenced: credit-service events added with AI assistance; see ai/usage-log.md.
class UserRegisteredEvent(BaseModel):
    """Published by user-service after email verification so that credit-service
    can provision the account's initial credit balance (Credit F1.1)."""

    user_id: str
    email: str


class CreditEventType(str, Enum):
    CREDIT_RESERVATION_ACCEPTED = "CreditReservationAccepted"
    CREDIT_RESERVATION_REJECTED = "CreditReservationRejected"


class ReservationEvent(BaseModel):
    """Published by credit-service after a reservation is accepted (Credit
    F2.1.4) or rejected (Credit F2.1.5)."""

    event_type: CreditEventType
    reservation_id: str | None
    user_id: str
    order_id: str
    amount: int
    timestamp: datetime
    reason: str | None = None

# AI-INFLUENCED: Pending Order domain event contracts implemented with Codex.
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

OrderActionEventType = Literal[
    "OrderDeletionRequested",
    "OrderCancellationRequested",
    "OrderExpiryRequested",
]


class OrderActionEvent(BaseModel):
    """An Order Service fact published while a terminal action is pending."""

    model_config = ConfigDict(extra="forbid")

    event_type: OrderActionEventType
    task_id: str
    order_id: str
    reservation_id: str
    requester_id: str
    timestamp: datetime
    reason: str | None = None


class OrderCancellationFailedEvent(BaseModel):
    """Final Order Service outcome after cancellation cannot be completed."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["OrderCancellationFailed"] = "OrderCancellationFailed"
    task_id: str
    order_id: str
    reservation_id: str
    requester_id: str
    timestamp: datetime
    reason: str


class OrderDeletedEvent(BaseModel):
    """Final Order Service outcome after an order has been deleted."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["OrderDeleted"] = "OrderDeleted"
    task_id: str
    order_id: str
    reservation_id: str
    requester_id: str
    timestamp: datetime


class OrderDeletionFailedEvent(BaseModel):
    """Final Order Service outcome after deletion cannot be completed."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["OrderDeletionFailed"] = "OrderDeletionFailed"
    task_id: str
    order_id: str
    reservation_id: str
    requester_id: str
    timestamp: datetime
    reason: str


OrderLocalOutcomeEvent = OrderCancellationFailedEvent | OrderDeletedEvent | OrderDeletionFailedEvent

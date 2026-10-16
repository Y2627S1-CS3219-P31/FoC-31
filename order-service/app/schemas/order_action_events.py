# AI-INFLUENCED: Pending Order domain event contracts implemented with Codex.
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

OrderActionEventType = Literal["OrderDelete", "OrderCancellationRequested", "OrderExpired"]


class OrderActionEvent(BaseModel):
    """An Order Service fact published while a terminal action is pending."""

    model_config = ConfigDict(extra="forbid")

    event_type: OrderActionEventType
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

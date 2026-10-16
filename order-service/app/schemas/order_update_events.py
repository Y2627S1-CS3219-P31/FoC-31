# AI-INFLUENCED: Order update event contract implemented with Codex.
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class OrderUpdateEvent(BaseModel):
    """Fact published when Order Service has accepted a pending update."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["OrderUpdate"] = "OrderUpdate"
    task_id: str
    order_id: str
    reservation_id: str
    requester_id: str
    reward: int
    timestamp: datetime


class OrderUpdatedEvent(BaseModel):
    """Final Order Service outcome after a pending update is applied."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["OrderUpdated"] = "OrderUpdated"
    task_id: str
    order_id: str
    reservation_id: str
    requester_id: str
    timestamp: datetime


class OrderUpdateFailedEvent(BaseModel):
    """Final Order Service outcome after a pending update is rejected."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["OrderUpdateFailed"] = "OrderUpdateFailed"
    task_id: str
    order_id: str
    reservation_id: str
    requester_id: str
    timestamp: datetime
    reason: str


OrderUpdateOutcomeEvent = OrderUpdatedEvent | OrderUpdateFailedEvent

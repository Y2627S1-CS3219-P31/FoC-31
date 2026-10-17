# AI-INFLUENCED: Order approval event contracts implemented with Codex.
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class OrderApprovalRequestedEvent(BaseModel):
    """Fact that Order Service has recorded a pending approval."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["OrderApprovalRequested"] = "OrderApprovalRequested"
    task_id: str
    order_id: str
    reservation_id: str
    requester_id: str
    courier_id: str
    timestamp: datetime


class OrderApprovedEvent(BaseModel):
    """Fact that Order Service completed an approved order."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["OrderApproved"] = "OrderApproved"
    task_id: str
    order_id: str
    reservation_id: str
    requester_id: str
    courier_id: str
    timestamp: datetime


class OrderApprovalFailedEvent(BaseModel):
    """Fact that Order Service could not complete an approval."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["OrderApprovalFailed"] = "OrderApprovalFailed"
    task_id: str
    order_id: str
    reservation_id: str
    requester_id: str
    timestamp: datetime
    reason: str


OrderApprovalEvent = OrderApprovalRequestedEvent | OrderApprovedEvent | OrderApprovalFailedEvent

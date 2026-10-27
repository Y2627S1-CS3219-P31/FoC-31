# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Local copy of the Order <-> Credit interop event contracts.

These mirror the schemas on the Order Service side
(`order-service/app/schemas/order_action_events.py`,
`order_update_events.py`, `order_approval_events.py` and `credit_events.py`).
They will move to `shared/foc_shared/events.py` (agreed with the Order Service
owner); until then credit-service keeps this single local copy so the two sides
cannot drift.

Deviation: `OrderExpiryRequested` is left out of `OrderActionEvent`. The Order
Service confirmed it is dead code (expiry is signalled by `OrderExpired`) and
is being removed; credit-service does not bind that routing key either.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

RELEASE_REQUEST_EVENT_TYPES = ("OrderDeletionRequested", "OrderCancellationRequested")


class OrderActionEvent(BaseModel):
    """Order -> Credit: release the reservation for a pending delete/cancel."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["OrderDeletionRequested", "OrderCancellationRequested"]
    task_id: str
    order_id: str
    reservation_id: str
    requester_id: str
    timestamp: datetime
    reason: str | None = None


class OrderUpdateRequestedEvent(BaseModel):
    """Order -> Credit: amend the reservation to the requested reward."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["OrderUpdateRequested"] = "OrderUpdateRequested"
    task_id: str
    order_id: str
    reservation_id: str
    requester_id: str
    reward: int
    timestamp: datetime


class OrderApprovalRequestedEvent(BaseModel):
    """Order -> Credit: transfer the reservation to the courier on approval."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["OrderApprovalRequested"] = "OrderApprovalRequested"
    task_id: str
    order_id: str
    reservation_id: str
    requester_id: str
    courier_id: str
    timestamp: datetime


class CreditReleaseResult(BaseModel):
    """Credit -> Order: outcome of a release request."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["CreditReleased", "CreditReleaseFailed"]
    task_id: str
    order_id: str | None = None
    reservation_id: str
    timestamp: datetime
    reason: str | None = None


class CreditAmendResult(BaseModel):
    """Credit -> Order: outcome of an amendment request."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["CreditAmended", "CreditAmendRejected"]
    task_id: str
    order_id: str | None = None
    reservation_id: str
    requester_id: str
    amount: int
    reason: str | None = None


class CreditTransferResult(BaseModel):
    """Credit -> Order: outcome of an approval transfer request.

    Mirrors ``order-service/app/schemas/credit_events.py::CreditTransferResult``
    exactly: six fields and ``extra="forbid"``. In particular there is **no**
    ``requester_id`` or ``amount`` here — adding one would make the Order
    consumer reject the reply.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["CreditTransferSucceeded", "CreditTransferFailed"]
    task_id: str
    order_id: str
    reservation_id: str
    timestamp: datetime
    reason: str | None = None


CreditResultEvent = CreditReleaseResult | CreditAmendResult | CreditTransferResult

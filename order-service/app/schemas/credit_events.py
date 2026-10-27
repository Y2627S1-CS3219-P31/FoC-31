# AI-INFLUENCED: Order-side credit integration event contracts implemented with Codex.
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CreditReleaseResult(BaseModel):
    """Order-side validator for either credit-release outcome event."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["CreditReleased", "CreditReleaseFailed"]
    task_id: str
    order_id: str | None = None
    reservation_id: str
    timestamp: datetime
    reason: str | None = None


class CreditAmendResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["CreditAmended", "CreditAmendRejected"]
    task_id: str
    order_id: str | None = None
    reservation_id: str
    requester_id: str
    amount: int
    reason: str | None = None


class CreditTransferResult(BaseModel):
    """Order-side validator for either credit-transfer outcome event."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["CreditTransferSucceeded", "CreditTransferFailed"]
    task_id: str
    order_id: str
    reservation_id: str
    timestamp: datetime
    reason: str | None = None

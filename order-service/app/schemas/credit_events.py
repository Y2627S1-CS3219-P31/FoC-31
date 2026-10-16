# AI-INFLUENCED: Order-side credit integration event contracts implemented with Codex.
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CreditReleaseResult(BaseModel):
    """Order-side validator for either credit-release outcome event."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["CreditReleased", "CreditReleaseFailed"]
    reservation_id: str
    timestamp: datetime
    reason: str | None = None

# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TransactionResponse(BaseModel):
    """Credit F5.1.2: amount (signed), timestamp, associated users."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    amount: int
    counterparty_user_id: str | None
    reservation_id: str | None
    order_id: str | None
    created_at: datetime

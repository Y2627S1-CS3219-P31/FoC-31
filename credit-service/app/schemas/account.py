# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BalanceResponse(BaseModel):
    """Credit F1.3 (reserved) + F1.4 (available)."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    available_balance: int
    reserved_balance: int

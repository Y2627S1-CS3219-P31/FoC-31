# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReservationCreate(BaseModel):
    """Credit F2: reserve credits when an order is created."""

    user_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    amount: int = Field(gt=0)


class AmendRequest(BaseModel):
    """Credit F2.3: new reward amount for an existing reservation."""

    amount: int = Field(gt=0)


class TransferRequest(BaseModel):
    """Credit F3: courier receiving the reserved credits."""

    courier_id: str = Field(min_length=1)


class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    order_id: str
    amount: int
    status: str
    created_at: datetime
    updated_at: datetime

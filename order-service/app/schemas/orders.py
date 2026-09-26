# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class OrderCreate(BaseModel):
    name: NonEmptyString
    details: NonEmptyString
    reward: int = Field(gt=0)
    deadline: datetime
    supplier_id: NonEmptyString
    pickup_location: NonEmptyString
    delivery_location: NonEmptyString

    @field_validator("deadline")
    @classmethod
    def deadline_must_be_future(cls, deadline: datetime) -> datetime:
        if deadline.tzinfo is None or deadline.utcoffset() is None:
            raise ValueError("deadline must include a timezone")
        if deadline <= datetime.now(UTC):
            raise ValueError("deadline must be in the future")
        return deadline


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    details: str
    reward: int
    deadline: datetime
    supplier_id: str
    pickup_location: str
    delivery_location: str
    requester_id: str
    courier_id: str | None
    status: str

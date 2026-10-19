# AI-INFLUENCED: Sprint 1 order schemas and validation implemented with Codex.
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from app.services.lifecycle import OrderStatus

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class OrderSortField(str, Enum):
    DEADLINE = "deadline"
    REWARD = "reward"


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


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
    def deadline_must_be_in_the_future(cls, deadline: datetime) -> datetime:
        if deadline.tzinfo is None or deadline.utcoffset() is None:
            raise ValueError("deadline must include a timezone")
        if deadline <= datetime.now(UTC):
            raise ValueError("deadline must be in the future")
        return deadline


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: str
    name: str
    details: str
    reward: int
    deadline: datetime
    supplier_id: str
    requester_id: str
    courier_id: str | None
    pickup_location: str
    delivery_location: str
    status: OrderStatus
    created_at: datetime


class OrderDetailResponse(OrderResponse):
    proof_of_delivery_photo: str | None = None


class OrderActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    order_id: str
    status: str
    failure_reason: str | None = Field(default=None, validation_alias="last_error")


class OrderCancellationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


# The fields here are restricted to the fields that the client is authorized to edit
class OrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonEmptyString
    details: NonEmptyString
    reward: int = Field(gt=0)
    deadline: datetime
    supplier_id: NonEmptyString
    pickup_location: NonEmptyString
    delivery_location: NonEmptyString

    @field_validator("deadline")
    @classmethod
    def deadline_must_be_in_the_future(cls, deadline: datetime, info: ValidationInfo) -> datetime:
        if deadline.tzinfo is None or deadline.utcoffset() is None:
            raise ValueError("deadline must include a timezone")
        if not (info.context or {}).get("stored_update") and deadline <= datetime.now(UTC):
            raise ValueError("deadline must be in the future")
        return deadline

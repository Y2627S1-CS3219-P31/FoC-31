from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class Category(str, Enum):
    FOOD = "Food"
    FOOD_COFFEE = "Food/Coffee"
    SHOPPING = "Shopping"
    PRINTING = "Printing"


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class SupplierCreate(_CamelModel):
    name: str = Field(min_length=1)
    category: Category
    building: str = Field(min_length=1)
    floor: str | None = None
    location_description: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    starting_time: str | None = Field(default=None, pattern=TIME_PATTERN)
    closing_time: str | None = Field(default=None, pattern=TIME_PATTERN)
    image_url: str | None = None


class SupplierUpdate(_CamelModel):
    name: str | None = Field(default=None, min_length=1)
    category: Category | None = None
    building: str | None = Field(default=None, min_length=1)
    floor: str | None = None
    location_description: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    starting_time: str | None = Field(default=None, pattern=TIME_PATTERN)
    closing_time: str | None = Field(default=None, pattern=TIME_PATTERN)
    image_url: str | None = None

    _REQUIRED_FIELDS = ("name", "category", "building")

    @model_validator(mode="after")
    def _reject_explicit_null_required(self) -> SupplierUpdate:
        cleared = [
            f
            for f in self._REQUIRED_FIELDS
            if f in self.model_fields_set and getattr(self, f) is None
        ]
        if cleared:
            raise ValueError(f"{', '.join(cleared)} cannot be null.")
        return self


class Supplier(_CamelModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: str
    name: str
    category: Category
    building: str
    floor: str | None = None
    location_description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    starting_time: str | None = None
    closing_time: str | None = None
    image_url: str | None = None
    active: bool


class SupplierList(BaseModel):
    items: list[Supplier]
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

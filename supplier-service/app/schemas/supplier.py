from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


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


class SupplierUpdate(_CamelModel):
    name: str | None = None
    category: Category | None = None
    building: str | None = None
    floor: str | None = None
    location_description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    starting_time: str | None = None
    closing_time: str | None = None
    image_url: str | None = None


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

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.supplier import Category, Supplier, SupplierCreate, SupplierUpdate


def test_category_enum_values():
    assert {c.value for c in Category} == {"Food", "Food/Coffee", "Shopping", "Printing"}


def test_create_requires_mandatory_fields():
    with pytest.raises(ValidationError):
        SupplierCreate(name="X", category="Food")  # missing building


def test_create_rejects_bad_category():
    with pytest.raises(ValidationError):
        SupplierCreate(name="X", category="Drinks", building="COM2")


def test_create_forbids_unknown_fields():
    with pytest.raises(ValidationError):
        SupplierCreate(name="X", category="Food", building="COM2", campusLocation="oops")


def test_supplier_serializes_camelcase():
    s = Supplier(
        id="sup_001",
        name="Anna's",
        category="Food",
        building="Central Library",
        locationDescription="Next to NUS Co-op",
        imageUrl="http://x/y.jpg",
        active=True,
    )
    dumped = s.model_dump(by_alias=True)
    assert dumped["locationDescription"] == "Next to NUS Co-op"
    assert dumped["imageUrl"] == "http://x/y.jpg"
    assert "location_description" not in dumped


def test_update_all_optional():
    u = SupplierUpdate(name="New Name")
    assert u.name == "New Name"
    # only set fields are exported
    assert u.model_dump(exclude_unset=True, by_alias=True) == {"name": "New Name"}


def test_update_omitting_required_fields_is_allowed():
    # not providing them at all is fine (partial update)
    u = SupplierUpdate(floor="2")
    assert u.model_dump(exclude_unset=True) == {"floor": "2"}


@pytest.mark.parametrize("field", ["name", "category", "building"])
def test_update_rejects_explicit_null_on_required_fields(field):
    with pytest.raises(ValidationError):
        SupplierUpdate(**{field: None})


def test_update_allows_explicit_null_on_optional_fields():
    u = SupplierUpdate(floor=None, imageUrl=None)
    dumped = u.model_dump(exclude_unset=True, by_alias=True)
    assert dumped == {"floor": None, "imageUrl": None}


@pytest.mark.parametrize("field", ["name", "building"])
def test_create_rejects_empty_required_string(field):
    body = {"name": "X", "category": "Food", "building": "COM2"}
    body[field] = ""
    with pytest.raises(ValidationError):
        SupplierCreate(**body)


@pytest.mark.parametrize("lat", [999, -91, 90.001])
def test_create_rejects_out_of_range_latitude(lat):
    with pytest.raises(ValidationError):
        SupplierCreate(name="X", category="Food", building="COM2", latitude=lat)


@pytest.mark.parametrize("lon", [999, -181, 180.001])
def test_create_rejects_out_of_range_longitude(lon):
    with pytest.raises(ValidationError):
        SupplierCreate(name="X", category="Food", building="COM2", longitude=lon)


@pytest.mark.parametrize("value", ["banana", "0900hrs", "24:00", "9:00", "23:60", "0900"])
def test_create_rejects_bad_time_format(value):
    with pytest.raises(ValidationError):
        SupplierCreate(name="X", category="Food", building="COM2", startingTime=value)


@pytest.mark.parametrize("value", ["00:00", "09:00", "23:59"])
def test_create_accepts_hhmm_time(value):
    s = SupplierCreate(
        name="X", category="Food", building="COM2", startingTime=value, closingTime=value
    )
    assert s.starting_time == value
    assert s.closing_time == value


def test_create_accepts_boundary_coordinates():
    s = SupplierCreate(name="X", category="Food", building="COM2", latitude=90, longitude=-180)
    assert s.latitude == 90
    assert s.longitude == -180


@pytest.mark.parametrize("field", ["name", "building"])
def test_update_rejects_empty_required_string(field):
    with pytest.raises(ValidationError):
        SupplierUpdate(**{field: ""})


def test_update_rejects_bad_time_format():
    with pytest.raises(ValidationError):
        SupplierUpdate(startingTime="banana")

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

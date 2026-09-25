from __future__ import annotations

from sqlalchemy import select

from app.models.supplier import Supplier


async def test_supplier_defaults_active_true(session):
    supplier = Supplier(id="sup_001", name="Anna's", category="Food", building="Central Library")
    session.add(supplier)
    await session.commit()

    row = (await session.execute(select(Supplier).where(Supplier.id == "sup_001"))).scalar_one()
    assert row.name == "Anna's"
    assert row.category == "Food"
    assert row.building == "Central Library"
    assert row.active is True
    assert row.floor is None
    assert row.latitude is None


async def test_supplier_optional_fields_persist(session):
    supplier = Supplier(
        id="sup_002",
        name="Cool Spot",
        category="Food",
        building="Com2",
        floor="1",
        location_description="Opp LT16",
        latitude=1.2940156,
        longitude=103.7738478,
        starting_time="0900hrs",
        closing_time="2130hrs",
        image_url=None,
        active=False,
    )
    session.add(supplier)
    await session.commit()

    row = (await session.execute(select(Supplier).where(Supplier.id == "sup_002"))).scalar_one()
    assert row.location_description == "Opp LT16"
    assert row.latitude == 1.2940156
    assert row.active is False

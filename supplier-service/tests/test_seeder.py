from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from app.models.supplier import Supplier
from app.services import seeder

CSV = Path(__file__).resolve().parents[2] / "data" / "csv" / "supplier-seed-data.csv"


async def _count(session) -> int:
    return await session.scalar(select(func.count()).select_from(Supplier))


async def test_seed_loads_all_rows(session):
    inserted = await seeder.seed_suppliers(session=session, csv_path=CSV)
    assert inserted == 21
    assert await _count(session) == 21


async def test_seed_is_idempotent(session):
    await seeder.seed_suppliers(session=session, csv_path=CSV)
    first = await _count(session)
    inserted_again = await seeder.seed_suppliers(session=session, csv_path=CSV)
    assert inserted_again == 0
    assert await _count(session) == first


async def test_seed_maps_columns(session):
    await seeder.seed_suppliers(session=session, csv_path=CSV)
    row = (
        await session.execute(select(Supplier).where(Supplier.name == "Anna's x Soup Union"))
    ).scalar_one()
    assert row.category == "Food"
    assert row.building == "Central Library"
    assert row.floor == "1"
    assert row.location_description == "Next to NUS Co-op"
    assert row.latitude == 1.296444
    assert row.starting_time == "0900hrs"
    assert row.active is True


async def test_seed_blank_imageurl_is_none(session):
    await seeder.seed_suppliers(session=session, csv_path=CSV)
    row = (
        await session.execute(select(Supplier).where(Supplier.name == "A Hot Hideout"))
    ).scalar_one()
    assert row.image_url is None

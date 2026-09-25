from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models.supplier import Supplier

SEED_CSV_PATH = Path("/data/csv/supplier-seed-data.csv")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _to_float(value: str | None) -> float | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _stable_id(name: str, building: str) -> str:
    digest = hashlib.sha1(f"{name}|{building}".encode()).hexdigest()
    return f"sup_{digest[:12]}"


def _row_to_supplier(row: dict[str, str]) -> Supplier:
    name = _clean(row.get("Name")) or ""
    building = _clean(row.get("Building")) or ""
    return Supplier(
        id=_stable_id(name, building),
        name=name,
        category=_clean(row.get("Type")) or "",
        building=building,
        floor=_clean(row.get("Floor")),
        location_description=_clean(row.get("Location Description")),
        latitude=_to_float(row.get("Latitude")),
        longitude=_to_float(row.get("Longitude")),
        starting_time=_clean(row.get("StartingTime")),
        closing_time=_clean(row.get("ClosingTime")),
        image_url=_clean(row.get("ImageURL")),
        active=True,
    )


async def _seed(session: AsyncSession, csv_path: Path) -> int:
    # Source CSV is Windows-1252 encoded (contains cp1252 curly apostrophes,
    # e.g. "Prince George's Park"); decode with that codec to load it faithfully.
    with csv_path.open(newline="", encoding="cp1252") as fh:
        rows = list(csv.DictReader(fh))

    inserted = 0
    for row in rows:
        candidate = _row_to_supplier(row)
        if not candidate.name:
            continue
        exists = await session.get(Supplier, candidate.id)
        if exists is not None:
            continue
        session.add(candidate)
        inserted += 1
    await session.commit()
    return inserted


async def seed_suppliers(
    *, session: AsyncSession | None = None, csv_path: Path = SEED_CSV_PATH
) -> int:
    """Idempotently load the baseline supplier catalog.

    Returns the number of newly inserted rows. Existing rows (matched by a
    deterministic id derived from name + building) are left untouched, so
    re-running the seeder never duplicates data (backlog F4).
    """
    if session is not None:
        return await _seed(session, csv_path)
    async with SessionLocal() as owned_session:
        return await _seed(owned_session, csv_path)

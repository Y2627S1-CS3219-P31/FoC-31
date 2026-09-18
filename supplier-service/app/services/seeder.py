from __future__ import annotations

from pathlib import Path

SEED_CSV_PATH = Path("/data/csv/supplier-seed-data.csv")


async def seed_suppliers() -> None:
    raise NotImplementedError

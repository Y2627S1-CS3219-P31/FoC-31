from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier import Supplier as SupplierRow
from app.schemas.supplier import Supplier, SupplierCreate, SupplierList, SupplierUpdate


def _new_id() -> str:
    return f"sup_{uuid.uuid4().hex[:12]}"


class SupplierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: SupplierCreate, *, supplier_id: str | None = None) -> Supplier:
        row = SupplierRow(
            id=supplier_id or _new_id(),
            name=data.name,
            category=data.category.value,
            building=data.building,
            floor=data.floor,
            location_description=data.location_description,
            latitude=data.latitude,
            longitude=data.longitude,
            starting_time=data.starting_time,
            closing_time=data.closing_time,
            image_url=data.image_url,
            active=True,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return Supplier.model_validate(row)

    async def get(self, supplier_id: str) -> Supplier | None:
        row = await self._session.get(SupplierRow, supplier_id)
        return Supplier.model_validate(row) if row is not None else None

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        categories: list[str] | None = None,
        zone: str | None = None,
        q: str | None = None,
    ) -> SupplierList:
        conditions = [SupplierRow.active.is_(True)]
        if categories:
            conditions.append(SupplierRow.category.in_(categories))
        if zone:
            conditions.append(SupplierRow.building.ilike(f"%{zone}%"))
        if q:
            like = f"%{q}%"
            conditions.append(
                or_(
                    SupplierRow.name.ilike(like),
                    SupplierRow.building.ilike(like),
                    SupplierRow.location_description.ilike(like),
                )
            )

        total = await self._session.scalar(
            select(func.count()).select_from(SupplierRow).where(*conditions)
        )
        rows = (
            (
                await self._session.execute(
                    select(SupplierRow)
                    .where(*conditions)
                    .order_by(SupplierRow.name)
                    .limit(page_size)
                    .offset((page - 1) * page_size)
                )
            )
            .scalars()
            .all()
        )

        return SupplierList(
            items=[Supplier.model_validate(r) for r in rows],
            page=page,
            page_size=page_size,
            total=total or 0,
        )

    async def update(self, supplier_id: str, patch: SupplierUpdate) -> Supplier | None:
        row = await self._session.get(SupplierRow, supplier_id)
        if row is None:
            return None
        changes = patch.model_dump(exclude_unset=True)
        for field, value in changes.items():
            if field == "category" and value is not None:
                value = value.value if hasattr(value, "value") else value
            setattr(row, field, value)
        await self._session.commit()
        await self._session.refresh(row)
        return Supplier.model_validate(row)

    async def deactivate(self, supplier_id: str) -> Supplier | None:
        row = await self._session.get(SupplierRow, supplier_id)
        if row is None:
            return None
        row.active = False
        await self._session.commit()
        await self._session.refresh(row)
        return Supplier.model_validate(row)

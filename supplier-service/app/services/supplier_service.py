from __future__ import annotations

from app.errors import ConflictError, NotFoundError
from app.repositories.supplier_repo import SupplierRepository
from app.schemas.supplier import Supplier, SupplierCreate, SupplierList, SupplierUpdate


class SupplierService:
    def __init__(self, repo: SupplierRepository) -> None:
        self._repo = repo

    async def create(self, data: SupplierCreate) -> Supplier:
        return await self._repo.create(data)

    async def get(self, supplier_id: str) -> Supplier:
        supplier = await self._repo.get(supplier_id)
        if supplier is None:
            raise NotFoundError(f"Supplier '{supplier_id}' was not found.")
        return supplier

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        categories: list[str] | None = None,
        zone: str | None = None,
        q: str | None = None,
        sort: str = "name",
        order: str = "asc",
        include_inactive: bool = False,
    ) -> SupplierList:
        return await self._repo.list(
            page=page,
            page_size=page_size,
            categories=categories,
            zone=zone,
            q=q,
            sort=sort,
            order=order,
            include_inactive=include_inactive,
        )

    async def update(self, supplier_id: str, patch: SupplierUpdate) -> Supplier:
        updated = await self._repo.update(supplier_id, patch)
        if updated is None:
            raise NotFoundError(f"Supplier '{supplier_id}' was not found.")
        return updated

    async def deactivate(self, supplier_id: str) -> Supplier:
        current = await self._repo.get(supplier_id)
        if current is None:
            raise NotFoundError(f"Supplier '{supplier_id}' was not found.")
        if not current.active:
            raise ConflictError(f"Supplier '{supplier_id}' is already deactivated.")
        deactivated = await self._repo.deactivate(supplier_id)
        assert deactivated is not None  # existence just confirmed
        return deactivated

    async def reactivate(self, supplier_id: str) -> Supplier:
        current = await self._repo.get(supplier_id)
        if current is None:
            raise NotFoundError(f"Supplier '{supplier_id}' was not found.")
        if current.active:
            raise ConflictError(f"Supplier '{supplier_id}' is already active.")
        reactivated = await self._repo.reactivate(supplier_id)
        assert reactivated is not None  # existence just confirmed
        return reactivated

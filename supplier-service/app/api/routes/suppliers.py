from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_supplier_service, require_admin
from app.schemas.supplier import (
    Category,
    Supplier,
    SupplierCreate,
    SupplierList,
    SupplierUpdate,
)
from app.services.supplier_service import SupplierService

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


@router.get("", response_model=SupplierList)
async def list_suppliers(
    category: list[Category] | None = Query(default=None),
    zone: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: SupplierService = Depends(get_supplier_service),
) -> SupplierList:
    categories = [c.value for c in category] if category else None
    return await service.list(page=page, page_size=page_size, categories=categories, zone=zone, q=q)


@router.get("/{supplier_id}", response_model=Supplier)
async def get_supplier(
    supplier_id: str,
    service: SupplierService = Depends(get_supplier_service),
) -> Supplier:
    return await service.get(supplier_id)


@router.post("", response_model=Supplier, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    payload: SupplierCreate,
    service: SupplierService = Depends(get_supplier_service),
    _: str = Depends(require_admin),
) -> Supplier:
    return await service.create(payload)


@router.patch("/{supplier_id}", response_model=Supplier)
async def update_supplier(
    supplier_id: str,
    payload: SupplierUpdate,
    service: SupplierService = Depends(get_supplier_service),
    _: str = Depends(require_admin),
) -> Supplier:
    return await service.update(supplier_id, payload)


@router.post("/{supplier_id}/deactivate", response_model=Supplier)
async def deactivate_supplier(
    supplier_id: str,
    service: SupplierService = Depends(get_supplier_service),
    _: str = Depends(require_admin),
) -> Supplier:
    return await service.deactivate(supplier_id)

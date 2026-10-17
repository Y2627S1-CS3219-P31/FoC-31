from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, Depends, Header, Query, status

from app.api.deps import get_supplier_service, require_admin
from app.schemas.supplier import (
    Category,
    Supplier,
    SupplierCreate,
    SupplierList,
    SupplierUpdate,
)
from app.services.supplier_service import SupplierService
from foc_shared.auth import HEADER_USER_ROLE, Role

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


class SortField(str, Enum):
    NAME = "name"
    CATEGORY = "category"
    BUILDING = "building"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


@router.get("", response_model=SupplierList)
async def list_suppliers(
    category: list[Category] | None = Query(default=None),
    zone: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: SortField = Query(default=SortField.NAME),
    order: SortOrder = Query(default=SortOrder.ASC),
    include_inactive: bool = Query(default=False),
    service: SupplierService = Depends(get_supplier_service),
    x_user_role: str | None = Header(default=None, alias=HEADER_USER_ROLE),
) -> SupplierList:
    categories = [c.value for c in category] if category else None
    # Inactive suppliers are only visible to admins; clients always get the
    # active-only catalog regardless of the query parameter.
    show_inactive = include_inactive and x_user_role == Role.ADMIN.value
    return await service.list(
        page=page,
        page_size=page_size,
        categories=categories,
        zone=zone,
        q=q,
        sort=sort.value,
        order=order.value,
        include_inactive=show_inactive,
    )


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


@router.post("/{supplier_id}/reactivate", response_model=Supplier)
async def reactivate_supplier(
    supplier_id: str,
    service: SupplierService = Depends(get_supplier_service),
    _: str = Depends(require_admin),
) -> Supplier:
    return await service.reactivate(supplier_id)

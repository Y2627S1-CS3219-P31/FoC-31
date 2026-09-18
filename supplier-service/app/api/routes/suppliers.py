from __future__ import annotations

from fastapi import APIRouter, status

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_suppliers() -> dict[str, str]:
    return {"detail": "not implemented"}


@router.get("/{supplier_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_supplier(supplier_id: str) -> dict[str, str]:
    return {"detail": "not implemented"}


@router.post("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def create_supplier() -> dict[str, str]:
    return {"detail": "not implemented"}

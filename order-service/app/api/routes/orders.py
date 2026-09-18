from __future__ import annotations

from fastapi import APIRouter, status

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def create_order() -> dict[str, str]:
    return {"detail": "not implemented"}


@router.get("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_orders() -> dict[str, str]:
    return {"detail": "not implemented"}


@router.get("/{order_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_order(order_id: str) -> dict[str, str]:
    return {"detail": "not implemented"}


@router.post("/{order_id}/accept", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def accept_order(order_id: str) -> dict[str, str]:
    return {"detail": "not implemented"}

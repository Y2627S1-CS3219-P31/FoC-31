from __future__ import annotations

from fastapi import APIRouter, status

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("/{user_id}/balance", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_balance(user_id: str) -> dict[str, str]:
    return {"detail": "not implemented"}


@router.post("/reservations", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def reserve() -> dict[str, str]:
    return {"detail": "not implemented"}


@router.post("/reservations/{reservation_id}/transfer", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def transfer(reservation_id: str) -> dict[str, str]:
    return {"detail": "not implemented"}


@router.post("/reservations/{reservation_id}/release", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def release(reservation_id: str) -> dict[str, str]:
    return {"detail": "not implemented"}

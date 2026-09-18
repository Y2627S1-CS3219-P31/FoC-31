from __future__ import annotations

from fastapi import APIRouter, status

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/{user_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_notifications(user_id: str) -> dict[str, str]:
    return {"detail": "not implemented"}

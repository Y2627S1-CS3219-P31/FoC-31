from __future__ import annotations

from fastapi import APIRouter, status

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def register() -> dict[str, str]:
    return {"detail": "not implemented"}


@router.post("/login", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def login() -> dict[str, str]:
    return {"detail": "not implemented"}


@router.get("/me", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_profile() -> dict[str, str]:
    return {"detail": "not implemented"}

# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.orders import OrderCreate, OrderResponse
from app.services import orders as order_service
from foc_shared.auth import HEADER_USER_ID

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    order: OrderCreate,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderResponse:
    return await order_service.create_order(session, order, requester_id)


@router.get("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_orders() -> dict[str, str]:
    return {"detail": "not implemented"}


@router.get("/{order_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_order(order_id: str) -> dict[str, str]:
    return {"detail": "not implemented"}


@router.post("/{order_id}/accept", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def accept_order(order_id: str) -> dict[str, str]:
    return {"detail": "not implemented"}

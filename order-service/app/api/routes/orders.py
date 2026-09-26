# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.orders import OrderCreate, OrderResponse
from app.services import orders as order_service
from foc_shared.auth import HEADER_USER_ID
from foc_shared.errors import ErrorEnvelope

router = APIRouter(prefix="/orders", tags=["orders"])


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    error = ErrorEnvelope(code=code, message=message)
    return JSONResponse(status_code=status_code, content=error.model_dump())


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


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[OrderResponse]:
    return await order_service.list_available_orders(session, requester_id)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderResponse | JSONResponse:
    try:
        return await order_service.get_order_for_requester(session, order_id, requester_id)
    except order_service.OrderNotFoundError as error:
        return error_response(status.HTTP_404_NOT_FOUND, "not_found", str(error))
    except order_service.OrderAccessDeniedError as error:
        return error_response(status.HTTP_403_FORBIDDEN, "forbidden", str(error))


@router.post("/{order_id}/accept", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def accept_order(order_id: str) -> dict[str, str]:
    return {"detail": "not implemented"}

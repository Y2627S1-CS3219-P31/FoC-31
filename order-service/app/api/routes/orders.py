# AI-INFLUENCED: Sprint 1 Order Service routes implemented with Codex.
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.orders import OrderCreate, OrderResponse, OrderUpdate
from app.services import orders as order_service
from foc_shared.auth import HEADER_USER_ID

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    new_order: OrderCreate,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderResponse:
    return await order_service.create_order(
        new_order=new_order,
        requester_id=requester_id,
        session=session,
    )


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[OrderResponse]:
    return await order_service.list_available_orders(session, requester_id)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderResponse:
    return await order_service.get_order_for_requester(
        session,
        order_id,
        requester_id,
    )


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    order_id: str,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await order_service.delete_order_for_requester(
        session,
        order_id,
        requester_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{order_id}", status_code=status.HTTP_200_OK)
async def update_order(
    order_id: str,
    updated_order: OrderUpdate,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)]
):
    await order_service.update_order(
        order_id=order_id,
        updated_order=updated_order,
        requester_id=requester_id,
        session=session
    )

    return Response(status_code=status.HTTP_200_OK)

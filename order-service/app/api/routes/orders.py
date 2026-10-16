# AI-INFLUENCED: Sprint 1 Order Service routes implemented with Codex.
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.orders import (
    OrderActionTaskResponse,
    OrderCancellationRequest,
    OrderCreate,
    OrderDeletionResponse,
    OrderResponse,
    OrderUpdate,
)
from app.services import orders as order_service
from foc_shared.auth import HEADER_USER_ID, HEADER_USER_ROLE, Role

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/{order_id}/accept", response_model=OrderResponse)
async def accept_order(
    order_id: str,
    courier_id: Annotated[str, Header(alias=HEADER_USER_ID, min_length=1)],
    role: Annotated[str, Header(alias=HEADER_USER_ROLE)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderResponse:
    if role != Role.CLIENT.value:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only clients can accept orders as couriers."
        )
    return await order_service.accept_order(session, order_id, courier_id)


@router.post(
    "/{order_id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OrderActionTaskResponse,
)
async def cancel_order(
    order_id: str,
    cancellation: OrderCancellationRequest,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID, min_length=1)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderActionTaskResponse:
    return await order_service.cancel_order_for_requester(
        session,
        order_id,
        requester_id,
        cancellation.reason,
    )


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


@router.get("/deletions/{task_id}", response_model=OrderDeletionResponse)
async def get_deletion(
    task_id: str,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderDeletionResponse:
    return await order_service.get_deletion_for_requester(session, task_id, requester_id)


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OrderDeletionResponse,
)
async def delete_order(
    order_id: str,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderDeletionResponse:
    return await order_service.delete_order_for_requester(
        session,
        order_id,
        requester_id,
    )


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

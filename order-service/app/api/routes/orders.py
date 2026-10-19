# AI-influenced: Order Service routes; get_order accepts requester or assigned courier.
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.orders import (
    OrderActionResponse,
    OrderCancellationRequest,
    OrderCreate,
    OrderResponse,
    OrderSortField,
    OrderUpdate,
    SortDirection,
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
    """Assigns an available order to a courier."""

    if role != Role.CLIENT.value:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only clients can accept orders as couriers."
        )
    return await order_service.accept_order(session, order_id, courier_id)


@router.post("/{order_id}/pickup", response_model=OrderResponse)
async def pickup_order(
    order_id: str,
    courier_id: Annotated[str, Header(alias=HEADER_USER_ID, min_length=1)],
    role: Annotated[str, Header(alias=HEADER_USER_ROLE)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderResponse:
    """Marks an accepted order as picked up by its courier."""

    if role != Role.CLIENT.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only clients can pick up orders.")
    return await order_service.pickup_order(session, order_id, courier_id)


@router.post("/{order_id}/withdraw", response_model=OrderResponse)
async def withdraw_order(
    order_id: str,
    courier_id: Annotated[str, Header(alias=HEADER_USER_ID, min_length=1)],
    role: Annotated[str, Header(alias=HEADER_USER_ROLE)],
    request_id: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"\S")
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderResponse:
    """Reopens an accepted order while keeping its credit reservation."""

    if role != Role.CLIENT.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only clients can withdraw as couriers.")
    return await order_service.withdraw_order(session, order_id, courier_id, request_id)


@router.post("/{order_id}/deliver", response_model=OrderResponse)
async def deliver_order(
    order_id: str,
    courier_id: Annotated[str, Header(alias=HEADER_USER_ID, min_length=1)],
    role: Annotated[str, Header(alias=HEADER_USER_ROLE)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderResponse:
    """Marks a picked-up order delivered for approval."""

    if role not in {Role.CLIENT.value, Role.ADMIN.value}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Unsupported user role.")
    return await order_service.deliver_order(session, order_id, courier_id)


@router.post(
    "/{order_id}/approve",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OrderActionResponse,
)
async def approve_order(
    order_id: str,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID, min_length=1)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderActionResponse:
    """Starts requester approval for a delivered order."""

    return await order_service.approve_order_for_requester(session, order_id, requester_id)


@router.post(
    "/{order_id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OrderActionResponse,
)
async def cancel_order(
    order_id: str,
    cancellation: OrderCancellationRequest,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID, min_length=1)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderActionResponse:
    """Starts a cancellation task for the order."""

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
    """Creates an order and reserves its reward credits."""

    return await order_service.create_order(
        new_order=new_order,
        requester_id=requester_id,
        session=session,
    )


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
    category: Annotated[list[str] | None, Query()] = None,
    min_reward: Annotated[int | None, Query(ge=1)] = None,
    max_reward: Annotated[int | None, Query(ge=1)] = None,
    sort_by: Annotated[OrderSortField | None, Query()] = None,
    sort_order: Annotated[SortDirection | None, Query()] = None,
) -> list[OrderResponse]:
    """Lists available orders with optional filters and sorting."""

    if min_reward is not None and max_reward is not None and min_reward > max_reward:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="min_reward cannot exceed max_reward.",
        )

    options = {
        "categories": category,
        "min_reward": min_reward,
        "max_reward": max_reward,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }
    selected_options = {key: value for key, value in options.items() if value is not None}
    return await order_service.list_available_orders(session, requester_id, **selected_options)


@router.get("/assigned", response_model=list[OrderResponse])
async def list_assigned_orders(
    courier_id: Annotated[str, Header(alias=HEADER_USER_ID, min_length=1)],
    role: Annotated[str, Header(alias=HEADER_USER_ROLE)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[OrderResponse]:
    """Lists the courier's ongoing assigned orders."""

    if role != Role.CLIENT.value:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only clients can view assigned courier orders."
        )
    return await order_service.list_assigned_orders(session, courier_id)


@router.get("/requested/ongoing", response_model=list[OrderResponse])
async def list_requested_ongoing_orders(
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID, min_length=1)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[OrderResponse]:
    """Lists the requester's orders that are still in progress."""

    return await order_service.list_requested_ongoing_orders(session, requester_id)


@router.get("/requested/completed", response_model=list[OrderResponse])
async def list_requested_completed_orders(
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID, min_length=1)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[OrderResponse]:
    """Lists the requester's completed orders."""

    return await order_service.list_requested_completed_orders(session, requester_id)


@router.get("/assigned/completed", response_model=list[OrderResponse])
async def list_assigned_completed_orders(
    courier_id: Annotated[str, Header(alias=HEADER_USER_ID, min_length=1)],
    role: Annotated[str, Header(alias=HEADER_USER_ROLE)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[OrderResponse]:
    """Lists orders completed by the authenticated courier."""

    if role != Role.CLIENT.value:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only clients can view assigned courier orders."
        )
    return await order_service.list_assigned_completed_orders(session, courier_id)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    user_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderResponse:
    """Returns an order to its requester or assigned courier."""

    return await order_service.get_order_for_participant(
        session,
        order_id,
        user_id,
    )


@router.get(
    "/deletions/{task_id}",
    response_model=OrderActionResponse,
)
async def get_deletion(
    task_id: str,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderActionResponse:
    """Returns a deletion task's status and failure reason."""

    return await order_service.get_deletion_for_requester(session, task_id, requester_id)


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OrderActionResponse,
)
async def delete_order(
    order_id: str,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderActionResponse:
    """Starts an order deletion task."""

    return await order_service.delete_order_for_requester(
        session,
        order_id,
        requester_id,
    )


@router.get(
    "/updates/{task_id}",
    response_model=OrderActionResponse,
)
async def get_update(
    task_id: str,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderActionResponse:
    """Returns an update task's status and failure reason."""

    return await order_service.get_update_for_requester(session, task_id, requester_id)


@router.patch(
    "/{order_id}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OrderActionResponse,
)
async def update_order(
    order_id: str,
    updated_order: OrderUpdate,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderActionResponse:
    """Starts an order update requiring credit approval."""

    return await order_service.update_order(
        order_id=order_id, updated_order=updated_order, requester_id=requester_id, session=session
    )

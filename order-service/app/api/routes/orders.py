# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_credit_client, get_supplier_client
from app.clients.credits import CreditClient
from app.clients.suppliers import SupplierClient
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
    supplier_client: Annotated[SupplierClient, Depends(get_supplier_client)],
    credit_client: Annotated[CreditClient, Depends(get_credit_client)],
) -> OrderResponse | JSONResponse:
    try:
        return await order_service.create_order(
            session,
            order,
            requester_id,
            supplier_client,
            credit_client,
        )
    except order_service.SupplierNotFoundError as error:
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "supplier_not_found",
            str(error),
        )
    except order_service.SupplierInactiveError as error:
        return error_response(status.HTTP_409_CONFLICT, "supplier_inactive", str(error))
    except order_service.CreditReservationError as error:
        return error_response(status.HTTP_409_CONFLICT, "credit_reservation_failed", str(error))
    except order_service.DependencyUnavailableError as error:
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"{error.dependency}_service_unavailable",
            str(error),
        )


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[OrderResponse]:
    return await order_service.list_requester_orders(session, requester_id)


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


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    order_id: int,
    requester_id: Annotated[str, Header(alias=HEADER_USER_ID)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    try:
        await order_service.delete_order_for_requester(session, order_id, requester_id)
    except order_service.OrderNotFoundError as error:
        return error_response(status.HTTP_404_NOT_FOUND, "not_found", str(error))
    except order_service.OrderAccessDeniedError as error:
        return error_response(status.HTTP_403_FORBIDDEN, "forbidden", str(error))
    except order_service.OrderStateConflictError as error:
        return error_response(status.HTTP_409_CONFLICT, "invalid_order_state", str(error))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

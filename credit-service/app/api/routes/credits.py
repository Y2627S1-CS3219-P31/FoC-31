# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import Identity, get_credit_service, require_identity
from app.errors import ForbiddenError
from app.schemas.account import BalanceResponse
from app.schemas.reservation import (
    AmendRequest,
    ReservationCreate,
    ReservationResponse,
    TransferRequest,
)
from app.schemas.transaction import TransactionResponse
from app.services.credit_service import CreditService
from foc_shared.auth import Role

router = APIRouter(prefix="/credits", tags=["credits"])

ServiceDep = Annotated[CreditService, Depends(get_credit_service)]
IdentityDep = Annotated[Identity, Depends(require_identity)]


def _require_self_or_admin(identity: Identity, user_id: str) -> None:
    """Balance/history visibility: owner or admin (mirrors user-service N2.1)."""
    if identity.user_id != user_id and identity.role != Role.ADMIN.value:
        raise ForbiddenError("You may only view your own credit data.")


@router.get("/{user_id}/balance", response_model=BalanceResponse)
async def get_balance(
    user_id: str,
    identity: IdentityDep,
    service: ServiceDep,
) -> BalanceResponse:
    _require_self_or_admin(identity, user_id)
    return await service.get_balances(user_id)


@router.get("/{user_id}/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    user_id: str,
    identity: IdentityDep,
    service: ServiceDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[TransactionResponse]:
    _require_self_or_admin(identity, user_id)
    return await service.list_transactions(user_id, limit=limit, offset=offset)


@router.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def reserve(
    payload: ReservationCreate,
    identity: IdentityDep,
    service: ServiceDep,
) -> ReservationResponse:
    if identity.user_id != payload.user_id and identity.role != Role.ADMIN.value:
        raise ForbiddenError("You may only reserve credits for yourself.")
    return await service.reserve(
        user_id=payload.user_id, order_id=payload.order_id, amount=payload.amount
    )


@router.post("/reservations/{reservation_id}/amend", response_model=ReservationResponse)
async def amend(
    reservation_id: str,
    payload: AmendRequest,
    identity: IdentityDep,
    service: ServiceDep,
) -> ReservationResponse:
    return await service.amend(
        reservation_id,
        payload.amount,
        caller_user_id=identity.user_id,
        caller_role=identity.role,
    )


@router.post("/reservations/{reservation_id}/transfer", response_model=ReservationResponse)
async def transfer(
    reservation_id: str,
    payload: TransferRequest,
    identity: IdentityDep,
    service: ServiceDep,
) -> ReservationResponse:
    return await service.transfer(
        reservation_id,
        payload.courier_id,
        caller_user_id=identity.user_id,
        caller_role=identity.role,
    )


@router.post("/reservations/{reservation_id}/release", response_model=ReservationResponse)
async def release(
    reservation_id: str,
    identity: IdentityDep,
    service: ServiceDep,
) -> ReservationResponse:
    return await service.release(
        reservation_id,
        caller_user_id=identity.user_id,
        caller_role=identity.role,
    )

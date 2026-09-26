from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.otp import OtpVerifyRequest, OtpVerifyResponse, ResendOtpRequest, ResendOtpResponse
from app.schemas.user import (
    LoginRequest,
    LoginResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    RegisterRequest,
    RegisterResponse,
)
from app.services import security
from app.services.exceptions import (
    AccountEmailAlreadyVerifiedError,
    AccountNotFoundError,
    AccountNotVerifiedError,
    AccountSuspendedError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidOtpError,
)
from app.services.user import UserService
from foc_shared.auth import HEADER_USER_ID

router = APIRouter(prefix="/users", tags=["users"])

type SessionDep = Annotated[AsyncSession, Depends(get_session)]

UserIdHeaderDep = Annotated[str | None, Header(alias=HEADER_USER_ID)]


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, session: SessionDep,
) -> RegisterResponse:
    service = UserService(session)
    try:
        user = await service.register(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            contact_number=payload.contact_number,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="email already registered"
        ) from exc
    return RegisterResponse(id=user.id, email=user.email)


@router.post("/otp/verify", response_model=OtpVerifyResponse)
async def verify_otp(
    payload: OtpVerifyRequest, session: SessionDep
) -> OtpVerifyResponse:
    service = UserService(session)
    try:
        await service.verify_email(email=payload.email, code=payload.code)
    except InvalidOtpError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OtpVerifyResponse(verified=True)


@router.post("/otp/resend", response_model=ResendOtpResponse)
async def resend_otp(
    payload: ResendOtpRequest,
    session: SessionDep,
) -> ResendOtpResponse:
    service = UserService(session)
    try:
        await service.resend_otp(email=payload.email)
    except AccountNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no account with that email"
        ) from exc
    except AccountEmailAlreadyVerifiedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email already verified — log in instead",
        ) from exc
    return ResendOtpResponse()


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    session: SessionDep,
) -> LoginResponse:
    service = UserService(session)
    try:
        user = await service.authenticate(email=payload.email, password=payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid email or password"
        ) from exc
    except AccountSuspendedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="account suspended"
        ) from exc
    except AccountNotVerifiedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="email not verified"
        ) from exc

    token, expires_in = security.issue_access_token(user_id=user.id, role=user.role)
    return LoginResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=ProfileResponse)
async def get_profile(
    session: SessionDep,
    x_user_id: UserIdHeaderDep = None,
) -> ProfileResponse:
    if x_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing identity header"
        )
    service = UserService(session)
    user = await service.get_profile(x_user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return ProfileResponse.model_validate(user)


@router.patch("/me", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdateRequest,
    session: SessionDep,
    x_user_id: UserIdHeaderDep = None,
) -> ProfileResponse:
    if x_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing identity header"
        )
    service = UserService(session)
    user = await service.update_profile(
        x_user_id,
        display_name=payload.display_name,
        contact_number=payload.contact_number,
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return ProfileResponse.model_validate(user)
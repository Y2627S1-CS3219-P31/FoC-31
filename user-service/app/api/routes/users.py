from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.otp import OtpVerifyRequest, OtpVerifyResponse, ResendOtpRequest, ResendOtpResponse
from app.schemas.user import (
    AdminUserListResponse,
    AdminUserResponse,
    CreateAdminRequest,
    LoginRequest,
    LoginResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    RegisterRequest,
    RegisterResponse,
)
from app.services import security
from app.services.exceptions import (
    AccountNotVerifiedError,
    AccountSuspendedError,
    CannotModifyAdminError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidOtpError,
    NotificationDeliveryError,
    OtpRateLimitError,
    UserNotFoundError,
)
from app.services.user import UserService
from foc_shared.auth import HEADER_USER_ID, HEADER_USER_ROLE, Role

router = APIRouter(prefix="/users", tags=["users"])

type SessionDep = Annotated[AsyncSession, Depends(get_session)]

UserIdHeaderDep = Annotated[str | None, Header(alias=HEADER_USER_ID)]
UserRoleHeaderDep = Annotated[str | None, Header(alias=HEADER_USER_ROLE)]


def _require_admin(*, user_id: str | None, role: str | None) -> str:
    if not user_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing gateway identity headers",
        )
    if role != Role.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="administrator role required",
        )
    return user_id


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
    except OtpRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="please wait before requesting another code",
        ) from exc
    except NotificationDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="verification email could not be sent",
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
    except OtpRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="please wait before requesting another code",
        ) from exc
    except NotificationDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="verification email could not be sent",
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

    try:
        token, expires_in = security.issue_access_token(user_id=user.id, role=user.role)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication is not configured",
        ) from exc
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


@router.post("/admin", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_admin(
    payload: CreateAdminRequest,
    session: SessionDep,
    x_user_id: UserIdHeaderDep = None,
    x_user_role: UserRoleHeaderDep = None,
) -> AdminUserResponse:
    _require_admin(user_id=x_user_id, role=x_user_role)
    try:
        user = await UserService(session).create_admin(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            contact_number=payload.contact_number,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="email already registered"
        ) from exc
    return AdminUserResponse.model_validate(user)


@router.get("/admin", response_model=AdminUserListResponse)
async def list_all_users(
    session: SessionDep,
    limit: int = 50,
    offset: int = 0,
    x_user_id: UserIdHeaderDep = None,
    x_user_role: UserRoleHeaderDep = None,
) -> AdminUserListResponse:
    _require_admin(user_id=x_user_id, role=x_user_role)
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must not be negative")

    users, total = await UserService(session).list_users(limit=limit, offset=offset)
    return AdminUserListResponse(
        items=[AdminUserResponse.model_validate(user) for user in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/admin/{user_id}/suspend", response_model=AdminUserResponse)
async def suspend_user(
    user_id: str,
    session: SessionDep,
    x_user_id: UserIdHeaderDep = None,
    x_user_role: UserRoleHeaderDep = None,
) -> AdminUserResponse:
    actor_id = _require_admin(user_id=x_user_id, role=x_user_role)
    try:
        user = await UserService(session).set_suspended(
            user_id=user_id, suspended=True, actor_id=actor_id
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    except CannotModifyAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AdminUserResponse.model_validate(user)


@router.post("/admin/{user_id}/unsuspend", response_model=AdminUserResponse)
async def unsuspend_user(
    user_id: str,
    session: SessionDep,
    x_user_id: UserIdHeaderDep = None,
    x_user_role: UserRoleHeaderDep = None,
) -> AdminUserResponse:
    actor_id = _require_admin(user_id=x_user_id, role=x_user_role)
    try:
        user = await UserService(session).set_suspended(
            user_id=user_id, suspended=False, actor_id=actor_id
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    except CannotModifyAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AdminUserResponse.model_validate(user)

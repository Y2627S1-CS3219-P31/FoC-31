from __future__ import annotations

from app.schemas.otp import OtpVerifyRequest, OtpVerifyResponse, ResendOtpRequest, ResendOtpResponse
from app.schemas.user import (
    LoginRequest,
    LoginResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    RegisterRequest,
    RegisterResponse,
)

__all__ = [
    "RegisterRequest",
    "RegisterResponse",
    "LoginRequest",
    "LoginResponse",
    "ProfileResponse",
    "ProfileUpdateRequest",
    "ResendOtpRequest",
    "ResendOtpResponse",
    "OtpVerifyRequest",
    "OtpVerifyResponse",
]
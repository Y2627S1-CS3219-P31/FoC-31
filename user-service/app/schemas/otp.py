from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field

_OTP_CODE_LENGTH = 6


class ResendOtpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class ResendOtpResponse(BaseModel):
    message: str = "Verification code sent. Check your email."


class OtpVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    code: str = Field(min_length=_OTP_CODE_LENGTH, max_length=_OTP_CODE_LENGTH, pattern=r"^\d+$")


class OtpVerifyResponse(BaseModel):
    verified: bool
    message: str = "email verified"

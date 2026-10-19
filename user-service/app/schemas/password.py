from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.user import _PASSWORD_MIN_LENGTH, validate_password_strength

_OTP_CODE_LENGTH = 6


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, v: str) -> str:
        return v.strip().lower()


class ForgotPasswordResponse(BaseModel):
    message: str = "If an account exists for that email, a reset code has been sent."


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    code: str = Field(min_length=_OTP_CODE_LENGTH, max_length=_OTP_CODE_LENGTH, pattern=r"^\d+$")
    new_password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=72)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, v: str) -> str:
        return validate_password_strength(v)


class ResetPasswordResponse(BaseModel):
    message: str = "Password updated. You can now log in with your new password."

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from foc_shared.auth import Role

_ALLOWED_EMAIL_DOMAIN = "u.nus.edu"
_PASSWORD_MIN_LENGTH = 8

class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=72)
    display_name: str = Field(min_length=1, max_length=50)
    contact_number: str | None = Field(
        default=None, max_length=8, pattern=r"^[89]\d{7}$"
    )

    @field_validator("email")
    @classmethod
    def _validate_email_domain(cls, v: str) -> str:
        v = v.strip().lower()
        if not v.endswith(f"@{_ALLOWED_EMAIL_DOMAIN}"):
            raise ValueError(f"email must be a @{_ALLOWED_EMAIL_DOMAIN} address")
        return v

    @field_validator("password")
    @classmethod
    def _validate_password_strength(cls, v: str) -> str:
        if len(v) < _PASSWORD_MIN_LENGTH:
            raise ValueError(f"password must be at least {_PASSWORD_MIN_LENGTH} characters")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("password must contain both letters and digits")
        return v


class CreateAdminRequest(RegisterRequest):
    """Validated account details for an administrator created by an admin."""

class RegisterResponse(BaseModel):
    id: str
    email: EmailStr
    message: str = "Registered. Check your email for a verification code."


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    display_name: str
    contact_number: str | None
    role: Role
    email_verified: bool


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    display_name: str
    contact_number: str | None
    role: Role
    email_verified: bool
    is_suspended: bool
    created_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    total: int
    limit: int
    offset: int


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=50)
    contact_number: str | None = Field(
        default=None, max_length=8, pattern=r"^[89]\d{7}$"
    )

    @model_validator(mode="after")
    def _at_least_one_field(self) -> ProfileUpdateRequest:
        if self.display_name is None and self.contact_number is None:
            raise ValueError("at least one field must be provided")
        return self

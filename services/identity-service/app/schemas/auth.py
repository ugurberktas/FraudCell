"""Authentication, token, and current-user schemas."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.customer import normalize_turkish_gsm


class CustomerLoginOtpRequest(BaseModel):
    gsm: str

    @field_validator("gsm")
    @classmethod
    def normalize_gsm(cls, value: str) -> str:
        return normalize_turkish_gsm(value)


class CustomerLoginRequest(CustomerLoginOtpRequest):
    otp_code: str = Field(min_length=1)

    @field_validator("otp_code")
    @classmethod
    def normalize_otp(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("OTP code must not be empty")
        return stripped


class StaffLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class AuthUserResponse(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    email: str | None
    gsm: str | None
    role: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUserResponse

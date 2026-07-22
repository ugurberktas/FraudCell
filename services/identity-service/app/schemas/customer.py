"""Customer OTP and registration request schemas."""
from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


_EMAIL_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$",
    re.IGNORECASE,
)


def normalize_turkish_gsm(value: str) -> str:
    """Validate and normalize a Turkish mobile number to +905xxxxxxxxx."""
    compact = re.sub(r"[\s()-]", "", value.strip())
    if re.fullmatch(r"05\d{9}", compact):
        return f"+90{compact[1:]}"
    if re.fullmatch(r"(?:\+90|0090)5\d{9}", compact):
        return f"+90{compact[-10:]}"
    if re.fullmatch(r"5\d{9}", compact):
        return f"+90{compact}"
    raise ValueError("A valid Turkish GSM number is required")


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized or len(normalized) > 255 or not _EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("A valid email address is required")
    return normalized


class OtpRequest(BaseModel):
    gsm: str

    @field_validator("gsm")
    @classmethod
    def validate_gsm(cls, value: str) -> str:
        return normalize_turkish_gsm(value)


class CustomerRegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    gsm: str
    email: str | None = None
    otp_code: str = Field(min_length=1)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name must not be empty")
        return stripped

    @field_validator("gsm")
    @classmethod
    def validate_gsm(cls, value: str) -> str:
        return normalize_turkish_gsm(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return normalize_email(value)

    @field_validator("otp_code")
    @classmethod
    def validate_otp_code(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("OTP code must not be empty")
        return stripped


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    gsm: str
    email: str | None
    role: str

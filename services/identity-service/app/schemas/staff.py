"""Staff creation and safe response schemas."""
from __future__ import annotations

from enum import Enum
import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.security.passwords import validate_password_policy


class StaffRole(str, Enum):
    ANALYST = "ANALYST"
    SUPERVISOR = "SUPERVISOR"
    ADMIN = "ADMIN"


def _normalize_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        if not stripped:
            raise ValueError("List values must not be empty")
        if stripped not in seen:
            normalized.append(stripped)
            seen.add(stripped)
    return normalized


class StaffCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str
    role: StaffRole
    specializations: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    max_active_cases: int = Field(default=10, ge=1)

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name must not be empty")
        return stripped

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("password")
    @classmethod
    def enforce_password_policy(cls, value: str) -> str:
        validate_password_policy(value)
        return value

    @field_validator("specializations", "regions")
    @classmethod
    def normalize_list_values(cls, value: list[str]) -> list[str]:
        return _normalize_list(value)

    @model_validator(mode="after")
    def validate_analyst_profile(self) -> "StaffCreate":
        if self.role == StaffRole.ANALYST and not self.specializations:
            raise ValueError("ANALYST_SPECIALIZATION_REQUIRED")
        if self.role == StaffRole.ANALYST and not self.regions:
            raise ValueError("ANALYST_REGION_REQUIRED")
        return self


class StaffResponse(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    email: EmailStr
    role: StaffRole
    specializations: list[str]
    regions: list[str]
    max_active_cases: int

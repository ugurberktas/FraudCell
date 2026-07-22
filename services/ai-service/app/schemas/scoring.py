"""AI scoring and analyst profile schemas."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TransactionType(str, Enum):
    ODEME = "ODEME"
    TRANSFER = "TRANSFER"
    FATURA = "FATURA"
    CEKIM = "CEKIM"


class AssignmentStatus(str, Enum):
    ASSIGNED = "ASSIGNED"
    QUEUED = "QUEUED"


class ScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: uuid.UUID
    customer_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    transaction_type: TransactionType
    recipient: str = Field(min_length=1, max_length=255)
    source_device: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    occurred_at: datetime
    transaction_frequency_24h: int = Field(default=1, ge=1, le=1000)
    is_new_device: bool = False
    home_city: str | None = Field(default=None, max_length=100)

    @field_validator("recipient", "source_device", "city")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("home_city")
    @classmethod
    def trim_optional_city(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value.astimezone(timezone.utc)


class AnalystSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analyst_id: uuid.UUID
    specializations: list[str]
    regions: list[str]
    active_cases: int = Field(default=0, ge=0)
    max_active_cases: int = Field(default=10, gt=0)
    accuracy_rate: Decimal = Field(default=Decimal("0.8000"), ge=0, le=1)
    is_active: bool = True

    @field_validator("specializations", "regions")
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = value.strip().upper()
            if not item:
                raise ValueError("list values must not be blank")
            if item not in normalized:
                normalized.append(item)
        return normalized

    @model_validator(mode="after")
    def validate_capacity(self) -> "AnalystSyncRequest":
        if self.active_cases > self.max_active_cases:
            raise ValueError("active_cases cannot exceed max_active_cases")
        return self


class AnalystProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    analyst_id: uuid.UUID
    specializations: list[str]
    regions: list[str]
    active_cases: int
    max_active_cases: int
    accuracy_rate: Decimal
    is_active: bool
    updated_at: datetime

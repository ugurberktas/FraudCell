"""Transaction and risk case API schemas."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import (
    AIStatus,
    CaseStatus,
    CustomerResponse,
    FraudType,
    RiskLevel,
    TransactionDecision,
    TransactionType,
)


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

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

    @field_validator("occurred_at")
    @classmethod
    def require_utc_capable_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("home_city")
    @classmethod
    def trim_optional_home_city(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    transaction_number: str
    customer_id: uuid.UUID
    amount: Decimal
    transaction_type: TransactionType
    recipient: str
    source_device: str
    city: str
    occurred_at: datetime
    risk_score: Decimal | None
    fraud_type: FraudType
    decision: TransactionDecision
    risk_level: RiskLevel
    ai_status: AIStatus
    model_version: str | None
    temporary_blocked: bool
    created_at: datetime
    updated_at: datetime


class CaseDecision(str, Enum):
    ONAYLANDI = "ONAYLANDI"
    BLOKLANDI = "BLOKLANDI"


class CaseAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analyst_id: uuid.UUID


class CustomerResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response: CustomerResponse

    @field_validator("response")
    @classmethod
    def reject_no_response(cls, value: CustomerResponse) -> CustomerResponse:
        if value is CustomerResponse.YANIT_YOK:
            raise ValueError("response must be BEN_YAPTIM or BEN_YAPMADIM")
        return value


class CaseDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: CaseDecision
    note: str | None = Field(default=None, max_length=4000)

    @field_validator("note")
    @classmethod
    def trim_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class CaseHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_status: CaseStatus | None
    to_status: CaseStatus
    actor_user_id: uuid.UUID | None
    note: str | None
    created_at: datetime


class RiskCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    transaction_id: uuid.UUID
    status: CaseStatus
    assigned_analyst_id: uuid.UUID | None
    decision_note: str | None
    customer_response: CustomerResponse | None
    created_at: datetime
    assigned_at: datetime | None
    started_at: datetime | None
    verification_requested_at: datetime | None
    decided_at: datetime | None
    closed_at: datetime | None
    sla_due_at: datetime
    sla_remaining_seconds: int | None
    sla_exceeded: bool
    transaction: TransactionRead | None = None
    history: list[CaseHistoryRead] = Field(default_factory=list)

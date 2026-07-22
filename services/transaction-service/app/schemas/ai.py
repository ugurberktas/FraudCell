"""AI scoring interface schemas."""
from decimal import Decimal
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models import FraudType, RiskLevel, TransactionDecision


class AIScoringResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    risk_score: Decimal = Field(ge=0, le=1)
    fraud_type: FraudType
    decision: TransactionDecision
    risk_level: RiskLevel
    model_version: str | None = Field(default=None, max_length=100)
    assigned_analyst_id: uuid.UUID | None = None
    risk_reasons: list[str] = Field(default_factory=list)
    assignment_status: str = "QUEUED"
    assignment_score: Decimal | None = Field(default=None, ge=0, le=1)

from datetime import datetime
from enum import Enum
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Decision(str, Enum):
    ONAYLANDI = "ONAYLANDI"
    BLOKLANDI = "BLOKLANDI"


class CustomerResponse(str, Enum):
    BEN_YAPTIM = "BEN_YAPTIM"
    BEN_YAPMADIM = "BEN_YAPMADIM"
    YANIT_YOK = "YANIT_YOK"


class RiskLevel(str, Enum):
    DUSUK = "DUSUK"
    ORTA = "ORTA"
    YUKSEK = "YUKSEK"
    KRITIK = "KRITIK"
    BELIRSIZ = "BELIRSIZ"


class CaseDecisionData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: uuid.UUID
    transaction_id: uuid.UUID
    analyst_id: uuid.UUID
    decision: Decision
    fraud_type: str = Field(min_length=1, max_length=50)
    risk_level: RiskLevel
    customer_response: CustomerResponse
    case_created_at: datetime
    decided_at: datetime
    resolution_seconds: int = Field(ge=0)
    sla_exceeded: bool
    is_false_positive: bool

    @field_validator("case_created_at", "decided_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value


class FeedbackSubmittedData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback_id: uuid.UUID
    case_id: uuid.UUID
    customer_id: uuid.UUID
    rating: int = Field(ge=1, le=5)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def feedback_timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value

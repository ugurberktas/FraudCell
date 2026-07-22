"""Transaction and fraud case domain models."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TransactionType(str, Enum):
    ODEME = "ODEME"
    TRANSFER = "TRANSFER"
    FATURA = "FATURA"
    CEKIM = "CEKIM"


class FraudType(str, Enum):
    CALINTI_KART = "CALINTI_KART"
    HESAP_ELE_GECIRME = "HESAP_ELE_GECIRME"
    PARA_AKLAMA = "PARA_AKLAMA"
    SUPHELI_DAVRANIS = "SUPHELI_DAVRANIS"
    TEMIZ = "TEMIZ"


class TransactionDecision(str, Enum):
    ONAY = "ONAY"
    INCELEME = "INCELEME"
    BLOK = "BLOK"


class RiskLevel(str, Enum):
    DUSUK = "DUSUK"
    ORTA = "ORTA"
    YUKSEK = "YUKSEK"
    KRITIK = "KRITIK"
    BELIRSIZ = "BELIRSIZ"


class AIStatus(str, Enum):
    SCORED = "SCORED"
    UNAVAILABLE = "UNAVAILABLE"


class CaseStatus(str, Enum):
    YENI = "YENI"
    ATANDI = "ATANDI"
    INCELENIYOR = "INCELENIYOR"
    MUSTERI_DOGRULAMA = "MUSTERI_DOGRULAMA"
    ONAYLANDI = "ONAYLANDI"
    BLOKLANDI = "BLOKLANDI"
    KAPANDI = "KAPANDI"


class CustomerResponse(str, Enum):
    BEN_YAPTIM = "BEN_YAPTIM"
    BEN_YAPMADIM = "BEN_YAPMADIM"
    YANIT_YOK = "YANIT_YOK"


class TransactionNumberSequence(Base):
    __tablename__ = "transaction_number_sequences"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("transaction_number", name="uq_transactions_transaction_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    transaction_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    transaction_type: Mapped[TransactionType] = mapped_column(
        SQLEnum(TransactionType, name="transaction_type_enum"), nullable=False
    )
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    source_device: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    fraud_type: Mapped[FraudType] = mapped_column(
        SQLEnum(FraudType, name="fraud_type_enum"), nullable=False
    )
    decision: Mapped[TransactionDecision] = mapped_column(
        SQLEnum(TransactionDecision, name="transaction_decision_enum"), nullable=False
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        SQLEnum(RiskLevel, name="risk_level_enum"), nullable=False
    )
    ai_status: Mapped[AIStatus] = mapped_column(
        SQLEnum(AIStatus, name="ai_status_enum"), nullable=False
    )
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    temporary_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    risk_case: Mapped[RiskCase | None] = relationship(
        back_populates="transaction", uselist=False, cascade="all, delete-orphan"
    )


class RiskCase(Base):
    __tablename__ = "risk_cases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[CaseStatus] = mapped_column(
        SQLEnum(CaseStatus, name="case_status_enum"), nullable=False, default=CaseStatus.YENI
    )
    assigned_analyst_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_response: Mapped[CustomerResponse | None] = mapped_column(
        SQLEnum(CustomerResponse, name="customer_response_enum"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    transaction: Mapped[Transaction] = relationship(back_populates="risk_case")
    history: Mapped[list[CaseHistory]] = relationship(
        back_populates="risk_case",
        cascade="all, delete-orphan",
        order_by="CaseHistory.created_at",
    )


class CaseHistory(Base):
    __tablename__ = "case_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("risk_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[CaseStatus | None] = mapped_column(
        SQLEnum(CaseStatus, name="case_status_enum"), nullable=True
    )
    to_status: Mapped[CaseStatus] = mapped_column(
        SQLEnum(CaseStatus, name="case_status_enum"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    risk_case: Mapped[RiskCase] = relationship(back_populates="history")

"""Analyst capacity and matching profile."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, JSON, Numeric, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AnalystProfile(Base):
    __tablename__ = "analyst_profiles"
    __table_args__ = (
        CheckConstraint("active_cases >= 0", name="ck_analyst_profiles_active_cases"),
        CheckConstraint("max_active_cases > 0", name="ck_analyst_profiles_max_active_cases"),
        CheckConstraint(
            "accuracy_rate >= 0 AND accuracy_rate <= 1",
            name="ck_analyst_profiles_accuracy_rate",
        ),
    )

    analyst_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    specializations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    regions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    active_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_active_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    accuracy_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.8000")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

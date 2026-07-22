"""OtpChallenge model."""
from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlalchemy import DateTime, Enum as SQLEnum, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OtpPurpose(str, Enum):
    REGISTER = "REGISTER"
    LOGIN = "LOGIN"


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    gsm: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    purpose: Mapped[OtpPurpose] = mapped_column(
        SQLEnum(OtpPurpose, name="otp_purpose_enum"),
        nullable=False,
        default=OtpPurpose.REGISTER,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

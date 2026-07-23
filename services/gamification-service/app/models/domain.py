from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AnalystProfile(Base):
    __tablename__ = "analyst_profiles"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analyst_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True, index=True)
    total_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="BRONZ")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    badges: Mapped[list[Badge]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    score_entries: Mapped[list[ScoreLedger]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class ScoreLedger(Base):
    __tablename__ = "score_ledger"
    __table_args__ = (UniqueConstraint("event_id", "reason", name="uq_score_ledger_event_reason"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    analyst_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("analyst_profiles.analyst_id", ondelete="CASCADE"), nullable=False, index=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    profile: Mapped[AnalystProfile] = relationship(back_populates="score_entries")


class Badge(Base):
    __tablename__ = "badges"
    __table_args__ = (UniqueConstraint("analyst_id", "badge_code", name="uq_badges_analyst_code"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analyst_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("analyst_profiles.analyst_id", ondelete="CASCADE"), nullable=False, index=True)
    badge_code: Mapped[str] = mapped_column(String(50), nullable=False)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    source_event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    profile: Mapped[AnalystProfile] = relationship(back_populates="badges")

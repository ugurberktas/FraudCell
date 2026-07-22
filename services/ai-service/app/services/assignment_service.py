"""Deterministic analyst ranking and atomic capacity reservation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy.orm import Session

from app.repositories.analyst_repository import AnalystRepository
from app.schemas.scoring import AssignmentStatus


@dataclass(frozen=True)
class AssignmentResult:
    assigned_analyst_id: uuid.UUID | None
    assignment_status: AssignmentStatus
    assignment_score: float | None


class AssignmentService:
    def __init__(
        self,
        session: Session,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self.session = session
        self.clock = clock
        self.repository = AnalystRepository(session)

    @staticmethod
    def score(profile, fraud_type: str) -> float:
        specialization_match = float(
            fraud_type.upper() in {item.upper() for item in profile.specializations}
        )
        availability_ratio = max(
            0.0,
            min(1.0, 1.0 - profile.active_cases / profile.max_active_cases),
        )
        accuracy_rate = float(Decimal(profile.accuracy_rate))
        return (
            specialization_match * 0.50
            + availability_ratio * 0.30
            + accuracy_rate * 0.20
        )

    def assign(self, fraud_type: str) -> AssignmentResult:
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        while True:
            profiles = self.repository.list_eligible_for_update()
            if not profiles:
                return AssignmentResult(None, AssignmentStatus.QUEUED, None)
            ranked = sorted(
                profiles,
                key=lambda profile: (
                    -self.score(profile, fraud_type),
                    profile.active_cases,
                    str(profile.analyst_id),
                ),
            )
            reserved = False
            for profile in ranked:
                score = self.score(profile, fraud_type)
                active_cases = self.repository.reserve_capacity(profile, now)
                if active_cases is None:
                    continue
                profile.active_cases = active_cases
                reserved = True
                return AssignmentResult(
                    profile.analyst_id,
                    AssignmentStatus.ASSIGNED,
                    round(score, 6),
                )
            if not reserved:
                self.session.expire_all()
                return AssignmentResult(None, AssignmentStatus.QUEUED, None)

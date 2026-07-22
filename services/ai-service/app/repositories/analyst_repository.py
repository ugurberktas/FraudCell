"""Analyst profile persistence and capacity reservation."""
from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AnalystProfile
from app.schemas.scoring import AnalystSyncRequest


class AnalystRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, payload: AnalystSyncRequest, now: datetime) -> AnalystProfile:
        profile = self.session.get(AnalystProfile, payload.analyst_id)
        values = payload.model_dump()
        if profile is None:
            profile = AnalystProfile(**values, updated_at=now)
            self.session.add(profile)
            return profile
        for field, value in values.items():
            setattr(profile, field, value)
        profile.updated_at = now
        return profile

    def list_eligible_for_update(self) -> list[AnalystProfile]:
        statement = (
            select(AnalystProfile)
            .where(
                AnalystProfile.is_active.is_(True),
                AnalystProfile.active_cases < AnalystProfile.max_active_cases,
            )
            .with_for_update()
        )
        return list(self.session.scalars(statement))

    def reserve_capacity(
        self, profile: AnalystProfile, now: datetime
    ) -> int | None:
        statement = (
            update(AnalystProfile)
            .where(
                AnalystProfile.analyst_id == profile.analyst_id,
                AnalystProfile.is_active.is_(True),
                AnalystProfile.active_cases < AnalystProfile.max_active_cases,
            )
            .values(
                active_cases=AnalystProfile.active_cases + 1,
                updated_at=now,
            )
            .returning(AnalystProfile.active_cases)
        )
        return self.session.scalar(statement)

    def get(self, analyst_id: uuid.UUID) -> AnalystProfile | None:
        return self.session.get(AnalystProfile, analyst_id)

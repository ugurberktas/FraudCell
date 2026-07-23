from datetime import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import AnalystProfile, Badge, ProcessedEvent, ScoreLedger


class GamificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def is_processed(self, event_id: uuid.UUID) -> bool:
        return self.session.scalar(select(ProcessedEvent.id).where(ProcessedEvent.event_id == event_id)) is not None

    def get_profile(self, analyst_id: uuid.UUID, *, for_update: bool = False) -> AnalystProfile | None:
        statement = select(AnalystProfile).where(AnalystProfile.analyst_id == analyst_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def profiles(self) -> list[AnalystProfile]:
        return list(self.session.scalars(select(AnalystProfile).options(selectinload(AnalystProfile.badges))))

    def period_points(self, since: datetime) -> dict[uuid.UUID, int]:
        rows = self.session.execute(
            select(ScoreLedger.analyst_id, ScoreLedger.points).where(ScoreLedger.occurred_at >= since)
        )
        totals: dict[uuid.UUID, int] = {}
        for analyst_id, points in rows:
            totals[analyst_id] = totals.get(analyst_id, 0) + points
        return totals

    def recent_scores(self, analyst_id: uuid.UUID, limit: int = 10) -> list[ScoreLedger]:
        return list(self.session.scalars(
            select(ScoreLedger).where(ScoreLedger.analyst_id == analyst_id)
            .order_by(ScoreLedger.occurred_at.desc(), ScoreLedger.id.desc()).limit(limit)
        ))

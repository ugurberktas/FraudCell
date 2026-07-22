"""Analyst profile sync use case."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.repositories.analyst_repository import AnalystRepository
from app.schemas.scoring import AnalystProfileRead, AnalystSyncRequest


class AnalystService:
    def __init__(
        self,
        session: Session,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self.session = session
        self.clock = clock
        self.repository = AnalystRepository(session)

    def sync(self, payload: AnalystSyncRequest) -> dict:
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        try:
            profile = self.repository.upsert(payload, now)
            self.session.commit()
            stored = self.repository.get(profile.analyst_id)
            if stored is None:
                raise RuntimeError("Synced analyst profile could not be reloaded")
            return AnalystProfileRead.model_validate(stored).model_dump(mode="json")
        except Exception:
            self.session.rollback()
            raise

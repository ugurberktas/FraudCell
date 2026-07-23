"""Reset only demo analyst gamification state and related processed events."""
from __future__ import annotations

import os
import sys
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.cli.seed_demo_profiles import analyst_ids
from app.db.session import _get_engine
from app.models import AnalystProfile, Badge, ProcessedEvent, ScoreLedger


def _extra_event_ids() -> set[uuid.UUID]:
    values = set()
    for raw in os.getenv("DEMO_EVENT_IDS", "").split(","):
        if raw.strip():
            values.add(uuid.UUID(raw.strip()))
    return values


def reset(session: Session) -> tuple[int, int]:
    ids = analyst_ids()
    ledger_event_ids = set(session.scalars(select(ScoreLedger.event_id).where(ScoreLedger.analyst_id.in_(ids))))
    event_ids = ledger_event_ids | _extra_event_ids()
    session.execute(delete(Badge).where(Badge.analyst_id.in_(ids)))
    session.execute(delete(ScoreLedger).where(ScoreLedger.analyst_id.in_(ids)))
    if event_ids:
        session.execute(delete(ProcessedEvent).where(ProcessedEvent.event_id.in_(event_ids)))
    profiles = list(session.scalars(select(AnalystProfile).where(AnalystProfile.analyst_id.in_(ids))))
    for profile in profiles:
        profile.total_points = 0
        profile.resolved_cases = 0
        profile.level = "BRONZ"
    session.commit()
    return len(profiles), len(event_ids)


def main() -> int:
    try:
        with Session(_get_engine()) as session:
            profiles, events = reset(session)
        print(f"Gamification demo reset: {profiles} profiles, {events} processed events")
        return 0
    except Exception as exc:
        print(f"Gamification demo reset failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

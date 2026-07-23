import uuid

from sqlalchemy import func, select

from app.cli import seed_demo_profiles
from app.cli.reset_demo_profiles import reset
from app.models import AnalystProfile, Badge, ProcessedEvent, ScoreLedger
from datetime import datetime, timezone


def _env(monkeypatch):
    ids = [uuid.uuid4() for _ in range(3)]
    for name, value in zip(seed_demo_profiles.ID_ENVIRONMENTS, ids, strict=True):
        monkeypatch.setenv(name, str(value))
    return ids


def test_gamification_profile_seed_is_zero_and_idempotent(db, monkeypatch):
    ids = _env(monkeypatch)
    seed_demo_profiles.seed(db)
    seed_demo_profiles.seed(db)
    assert db.scalar(select(func.count()).select_from(AnalystProfile)) == 3
    profiles = list(db.scalars(select(AnalystProfile)))
    assert all(item.total_points == 0 and item.level == "BRONZ" for item in profiles)
    assert all(item.analyst_id in ids for item in profiles)


def test_gamification_reset_is_scoped_and_idempotent(db, monkeypatch):
    ids = _env(monkeypatch)
    seed_demo_profiles.seed(db)
    demo_event, real_event = uuid.uuid4(), uuid.uuid4()
    real_id = uuid.uuid4()
    real_profile = AnalystProfile(analyst_id=real_id, total_points=77, resolved_cases=1, level="BRONZ")
    db.add(real_profile)
    db.flush()
    db.add_all([
        ScoreLedger(event_id=demo_event, analyst_id=ids[0], points=10, reason="CASE_RESOLVED", occurred_at=datetime.now(timezone.utc)),
        ScoreLedger(event_id=real_event, analyst_id=real_id, points=10, reason="CASE_RESOLVED", occurred_at=datetime.now(timezone.utc)),
        Badge(analyst_id=ids[0], badge_code="ILK_YAKALAMA", source_event_id=demo_event),
        ProcessedEvent(event_id=demo_event, event_type="case.decision_made"),
        ProcessedEvent(event_id=real_event, event_type="case.decision_made"),
    ])
    demo_profile = db.scalar(select(AnalystProfile).where(AnalystProfile.analyst_id == ids[0]))
    demo_profile.total_points = 10
    demo_profile.resolved_cases = 1
    db.commit()
    assert reset(db) == (3, 1)
    assert reset(db) == (3, 0)
    assert db.get(AnalystProfile, real_profile.id).total_points == 77
    assert db.scalar(select(func.count()).select_from(ProcessedEvent)) == 1

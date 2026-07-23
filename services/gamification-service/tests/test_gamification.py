from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import uuid

import pytest
from sqlalchemy import func, select

from app.models import AnalystProfile, Badge, ProcessedEvent, ScoreLedger
from app.schemas.events import CaseDecisionData
from app.services.event_service import EventService, InvalidEvent
from app.services.scoring_service import level_for, score_case
from app.workers import event_consumer
from tests.conftest import auth, decision_event


def _data(**overrides):
    return CaseDecisionData.model_validate(decision_event(payload=overrides)["payload"])


@pytest.mark.parametrize(
    ("payload", "reason", "points"),
    [
        ({"decision": "ONAYLANDI", "resolution_seconds": 901, "risk_level": "DUSUK", "customer_response": "YANIT_YOK"}, "CASE_RESOLVED", 10),
        ({"decision": "ONAYLANDI", "resolution_seconds": 899, "risk_level": "DUSUK", "customer_response": "YANIT_YOK"}, "FAST_DECISION", 5),
        ({"decision": "BLOKLANDI", "customer_response": "BEN_YAPMADIM", "risk_level": "DUSUK", "resolution_seconds": 901}, "CONFIRMED_FRAUD", 15),
        ({"decision": "ONAYLANDI", "risk_level": "KRITIK", "sla_exceeded": False, "resolution_seconds": 901, "customer_response": "YANIT_YOK"}, "CRITICAL_WITHIN_SLA", 15),
        ({"decision": "ONAYLANDI", "risk_level": "DUSUK", "sla_exceeded": True, "resolution_seconds": 901, "customer_response": "YANIT_YOK"}, "SLA_EXCEEDED", -5),
        ({"decision": "BLOKLANDI", "risk_level": "DUSUK", "is_false_positive": True, "resolution_seconds": 901, "customer_response": "BEN_YAPTIM"}, "FALSE_POSITIVE", -8),
    ],
)
def test_independent_score_rules(payload, reason, points):
    awards = score_case(_data(**payload))
    assert any(item.reason.value == reason and item.points == points for item in awards)


def test_combined_demo_event_scores_45_and_awards_badge(db):
    event = decision_event()
    result = EventService(db).process(event)
    analyst_id = uuid.UUID(event["payload"]["analyst_id"])
    profile = db.scalar(select(AnalystProfile).where(AnalystProfile.analyst_id == analyst_id))
    assert result.points == 45 and profile.total_points == 45 and profile.resolved_cases == 1
    assert result.badge_earned is True
    assert db.scalar(select(Badge.badge_code)) == "ILK_YAKALAMA"
    assert set(db.scalars(select(ScoreLedger.reason))) == {
        "CASE_RESOLVED", "FAST_DECISION", "CONFIRMED_FRAUD", "CRITICAL_WITHIN_SLA"
    }


def test_duplicate_event_is_idempotent(db):
    event = decision_event()
    first = EventService(db).process(event)
    second = EventService(db).process(event)
    assert first.points == 45 and second.duplicate is True
    assert db.scalar(select(func.count()).select_from(ProcessedEvent)) == 1
    assert db.scalar(select(func.count()).select_from(ScoreLedger)) == 4


def test_first_catch_badge_is_only_awarded_once(db):
    event1 = decision_event()
    analyst_id = event1["payload"]["analyst_id"]
    event2 = decision_event(payload={"analyst_id": analyst_id})
    EventService(db).process(event1)
    result = EventService(db).process(event2)
    assert result.badge_earned is False
    assert db.scalar(select(func.count()).select_from(Badge)) == 1


@pytest.mark.parametrize(("points", "level"), [(-10, "BRONZ"), (0, "BRONZ"), (499, "BRONZ"), (500, "GUMUS"), (1499, "GUMUS"), (1500, "ALTIN"), (2999, "ALTIN"), (3000, "PLATIN")])
def test_level_boundaries(points, level):
    assert level_for(points) == level


def test_invalid_event_is_rejected(db):
    with pytest.raises(InvalidEvent):
        EventService(db).process(decision_event(event_version=2))


def test_feedback_event_is_processed_without_points_and_is_idempotent(db):
    now = datetime.now(timezone.utc)
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "feedback.submitted",
        "event_version": 1,
        "occurred_at": now.isoformat(),
        "producer": "transaction-service",
        "correlation_id": str(uuid.uuid4()),
        "payload": {
            "feedback_id": str(uuid.uuid4()),
            "case_id": str(uuid.uuid4()),
            "customer_id": str(uuid.uuid4()),
            "rating": 5,
            "created_at": now.isoformat(),
        },
    }
    first = EventService(db).process(event)
    second = EventService(db).process(event)
    assert first.points == 0 and first.duplicate is False
    assert second.duplicate is True
    assert db.scalar(select(func.count()).select_from(ProcessedEvent)) == 1
    assert db.scalar(select(func.count()).select_from(ScoreLedger)) == 0


def test_daily_weekly_leaderboard_and_profile(client, db):
    first = decision_event()
    first_id = uuid.UUID(first["payload"]["analyst_id"])
    second = decision_event(payload={"analyst_id": str(uuid.uuid4()), "risk_level": "DUSUK", "customer_response": "YANIT_YOK"})
    second_id = uuid.UUID(second["payload"]["analyst_id"])
    EventService(db).process(first)
    EventService(db).process(second)
    for period in ("daily", "weekly"):
        response = client.get(f"/leaderboard?period={period}&limit=10", headers=auth(first_id, "ANALYST"))
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert items[0]["analyst_id"] == str(first_id) and items[0]["period_points"] == 45
    profile = client.get("/profiles/me", headers=auth(first_id, "ANALYST"))
    assert profile.status_code == 200
    assert profile.json()["data"]["badges"] == ["ILK_YAKALAMA"]
    assert profile.json()["data"]["daily_rank"] == 1


def test_leaderboard_limit_is_at_most_ten(client):
    response = client.get("/leaderboard?limit=11", headers=auth(uuid.uuid4(), "ADMIN"))
    assert response.status_code == 422


def test_profile_rbac_and_idor(client, db):
    event = decision_event()
    target = uuid.UUID(event["payload"]["analyst_id"])
    EventService(db).process(event)
    assert client.get(f"/profiles/{target}", headers=auth(uuid.uuid4(), "SUPERVISOR")).status_code == 200
    assert client.get(f"/profiles/{target}", headers=auth(uuid.uuid4(), "ADMIN")).status_code == 200
    assert client.get(f"/profiles/{target}", headers=auth(uuid.uuid4(), "ANALYST")).status_code == 403
    assert client.get(f"/profiles/{target}", headers=auth(uuid.uuid4(), "CUSTOMER")).status_code == 403
    assert client.get("/leaderboard").status_code == 401


class _Method:
    delivery_tag = 7


class _Channel:
    def __init__(self):
        self.calls = []
    def basic_ack(self, **kwargs): self.calls.append(("ack", kwargs))
    def basic_reject(self, **kwargs): self.calls.append(("reject", kwargs))
    def basic_nack(self, **kwargs): self.calls.append(("nack", kwargs))


def test_consumer_acks_only_after_db_commit(monkeypatch, engine, db):
    channel = _Channel()
    event = decision_event()
    monkeypatch.setattr(event_consumer, "_get_engine", lambda: engine)
    event_consumer.handle_delivery(channel, _Method(), None, json.dumps(event).encode())
    assert channel.calls[0][0] == "ack"
    assert db.scalar(select(func.count()).select_from(ProcessedEvent)) == 1


def test_consumer_rejects_invalid_payload_without_requeue(monkeypatch, engine):
    channel = _Channel()
    monkeypatch.setattr(event_consumer, "_get_engine", lambda: engine)
    event_consumer.handle_delivery(channel, _Method(), None, b'{"bad":true}')
    assert channel.calls == [("reject", {"delivery_tag": 7, "requeue": False})]


def test_consumer_nacks_transient_db_failure(monkeypatch):
    channel = _Channel()
    class BrokenService:
        def __init__(self, session): pass
        def process(self, raw): raise RuntimeError("temporary db failure")
    class Context:
        def __enter__(self): return object()
        def __exit__(self, *args): return False
    monkeypatch.setattr(event_consumer, "Session", lambda *_: Context())
    monkeypatch.setattr(event_consumer, "EventService", BrokenService)
    event_consumer.handle_delivery(channel, _Method(), None, json.dumps(decision_event()).encode())
    assert channel.calls == [("nack", {"delivery_tag": 7, "requeue": True})]


def test_migration_has_upgrade_and_downgrade():
    path = Path(__file__).parents[1] / "alembic/versions/001_initial_gamification_schema.py"
    text = path.read_text()
    assert "def upgrade()" in text and "def downgrade()" in text

import uuid

import pytest
from sqlalchemy import func, select

from app.cli import seed_demo_analysts
from app.models import AnalystProfile


def _env(monkeypatch):
    values = [uuid.uuid4() for _ in range(3)]
    for (name, *_rest), value in zip(seed_demo_analysts.PROFILES, values, strict=True):
        monkeypatch.setenv(name, str(value))
    return values


def test_ai_demo_seed_is_idempotent_and_preserves_capacity(db, monkeypatch):
    _env(monkeypatch)
    first = seed_demo_analysts.seed(db)
    profile = db.get(AnalystProfile, uuid.UUID(first[0]["analyst_id"]))
    profile.active_cases = 4
    db.commit()
    second = seed_demo_analysts.seed(db)
    assert db.scalar(select(func.count()).select_from(AnalystProfile)) == 3
    assert db.get(AnalystProfile, profile.analyst_id).active_cases == 4
    assert first[0]["analyst_id"] == second[0]["analyst_id"]


def test_ai_demo_check_rejects_missing_profile(db, monkeypatch):
    _env(monkeypatch)
    with pytest.raises(ValueError, match="missing"):
        seed_demo_analysts.seed(db, create_missing=False)

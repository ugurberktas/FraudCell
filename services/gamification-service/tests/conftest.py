from datetime import datetime, timedelta, timezone
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_SECRET = "gamification-tests-dedicated-secret-2026"


@pytest.fixture
def engine():
    value = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(value)
    yield value
    Base.metadata.drop_all(value)
    value.dispose()


@pytest.fixture
def db_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def db(db_factory):
    with db_factory() as session:
        yield session


@pytest.fixture
def client(db_factory, monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", TEST_SECRET)
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")
    def override():
        with db_factory() as session:
            yield session
    app.dependency_overrides[get_db] = override
    with TestClient(app, raise_server_exceptions=False) as value:
        yield value
    app.dependency_overrides.clear()


def token(user_id: uuid.UUID, role: str) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id), "user_id": str(user_id), "role": role,
        "specializations": [], "regions": [], "type": "access",
        "jti": str(uuid.uuid4()), "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "iss": "fraudcell-identity", "aud": "fraudcell-platform",
    }
    return jwt.encode(claims, TEST_SECRET, algorithm="HS256")


def auth(user_id: uuid.UUID, role: str):
    return {"Authorization": f"Bearer {token(user_id, role)}"}


def decision_event(**overrides):
    now = datetime.now(timezone.utc)
    payload = {
        "case_id": str(uuid.uuid4()), "transaction_id": str(uuid.uuid4()),
        "analyst_id": str(uuid.uuid4()), "decision": "BLOKLANDI",
        "fraud_type": "CALINTI_KART", "risk_level": "KRITIK",
        "customer_response": "BEN_YAPMADIM",
        "case_created_at": (now - timedelta(minutes=5)).isoformat(),
        "decided_at": now.isoformat(), "resolution_seconds": 300,
        "sla_exceeded": False, "is_false_positive": False,
    }
    payload.update(overrides.pop("payload", {}))
    event = {
        "event_id": str(uuid.uuid4()), "event_type": "case.decision_made",
        "event_version": 1, "occurred_at": now.isoformat(),
        "producer": "transaction-service", "correlation_id": str(uuid.uuid4()),
        "payload": payload,
    }
    event.update(overrides)
    return event

from datetime import datetime, timedelta, timezone
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.clients.ai_client import AIServiceUnavailable, get_ai_client
from app.core.config import settings
from app.db.base import Base
from app.db.dependencies import get_db
from app.main import app
from app.models import FraudType, RiskLevel, TransactionDecision
from app.schemas.ai import AIScoringResult


TEST_JWT_SECRET = "transaction-tests-use-a-dedicated-secret-2026"


class FakeAIClient:
    def __init__(self, result: AIScoringResult | None = None, unavailable: bool = False):
        self.result = result or AIScoringResult(
            risk_score="0.95",
            fraud_type=FraudType.CALINTI_KART,
            decision=TransactionDecision.INCELEME,
            risk_level=RiskLevel.KRITIK,
            model_version="golden-test-v1",
            assigned_analyst_id=None,
        )
        self.unavailable = unavailable
        self.request_ids: list[str] = []

    def score_and_assign(self, **kwargs):
        self.request_ids.append(kwargs["request_id"])
        if self.unavailable:
            raise AIServiceUnavailable("test fallback")
        return self.result


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=True)


@pytest.fixture
def fake_ai():
    return FakeAIClient()


@pytest.fixture
def client(db_factory, fake_ai, monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(settings, "jwt_issuer", "fraudcell-identity")
    monkeypatch.setattr(settings, "jwt_audience", "fraudcell-platform")

    def override_db():
        with db_factory() as session:
            try:
                yield session
            finally:
                session.rollback()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_ai_client] = lambda: fake_ai
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db(db_factory):
    with db_factory() as session:
        yield session


def access_token(user_id: uuid.UUID, role: str, **overrides) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "user_id": str(user_id),
        "role": role,
        "specializations": [],
        "regions": [],
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "iss": "fraudcell-identity",
        "aud": "fraudcell-platform",
    }
    claims.update(overrides)
    return jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")


def auth(user_id: uuid.UUID, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token(user_id, role)}"}


def transaction_payload(**overrides) -> dict:
    payload = {
        "amount": 48500.00,
        "transaction_type": "TRANSFER",
        "recipient": "Demo Alıcı",
        "source_device": "iPhone 15 Pro",
        "city": "Berlin",
        "occurred_at": "2026-07-23T10:00:00Z",
    }
    payload.update(overrides)
    return payload

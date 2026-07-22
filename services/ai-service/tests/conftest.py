import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.dependencies import get_db
from app.main import app


TEST_INTERNAL_KEY = "fraudcell-ai-internal-test-key"


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
def db(db_factory):
    with db_factory() as session:
        yield session


@pytest.fixture
def client(db_factory, monkeypatch):
    monkeypatch.setattr(settings, "internal_service_key", TEST_INTERNAL_KEY)

    def override_db():
        with db_factory() as session:
            try:
                yield session
            finally:
                session.rollback()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def internal_headers() -> dict[str, str]:
    return {"X-Internal-Service-Key": TEST_INTERNAL_KEY}


def analyst_payload(analyst_id: uuid.UUID | None = None, **overrides) -> dict:
    payload = {
        "analyst_id": str(analyst_id or uuid.uuid4()),
        "specializations": ["CALINTI_KART"],
        "regions": ["TR"],
        "active_cases": 0,
        "max_active_cases": 10,
        "accuracy_rate": "0.9000",
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def score_payload(**overrides) -> dict:
    payload = {
        "transaction_id": str(uuid.uuid4()),
        "customer_id": str(uuid.uuid4()),
        "amount": "15000.00",
        "transaction_type": "TRANSFER",
        "recipient": "Demo Alıcı",
        "source_device": "New Android Device",
        "city": "Berlin",
        "occurred_at": "2026-07-23T16:00:00Z",
        "transaction_frequency_24h": 4,
        "is_new_device": True,
        "home_city": "Istanbul",
    }
    payload.update(overrides)
    return payload

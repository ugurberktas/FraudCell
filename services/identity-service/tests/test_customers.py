"""Tests for customer GSM normalization, OTP challenges, and registration."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.dependencies import get_db
from app.main import app
from app.models import Base, OtpChallenge, User, UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.customer import normalize_turkish_gsm


@pytest.fixture()
def database_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(database_engine):
    def override_get_db():
        with Session(database_engine) as session:
            try:
                yield session
            finally:
                session.rollback()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


def request_otp(client: TestClient, gsm: str = "05000000001"):
    return client.post("/customers/otp/request", json={"gsm": gsm})


def registration_payload(
    gsm: str = "05000000001", email: str | None = " Mail@Example.COM "
) -> dict:
    return {
        "first_name": " Uğur ",
        "last_name": " Berktaş ",
        "gsm": gsm,
        "email": email,
        "otp_code": "1234",
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("05000000001", "+905000000001"),
        ("+905000000001", "+905000000001"),
        ("00905000000001", "+905000000001"),
        ("500 000 00 01", "+905000000001"),
    ],
)
def test_gsm_normalization(raw: str, expected: str) -> None:
    assert normalize_turkish_gsm(raw) == expected


@pytest.mark.parametrize("gsm", ["", "12345", "04000000000", "+441234567890"])
def test_invalid_gsm_is_rejected(client: TestClient, gsm: str) -> None:
    response = request_otp(client, gsm)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_otp_challenge_is_created_without_code(client: TestClient, database_engine) -> None:
    first = request_otp(client)
    second = request_otp(client)

    assert first.status_code == 200
    body = second.json()
    assert body["success"] is True
    assert "1234" not in second.text
    assert "otp_code" not in second.text
    assert "would not be shown" in body["data"]["message"]

    with Session(database_engine) as session:
        challenges = session.scalars(
            select(OtpChallenge).order_by(OtpChallenge.created_at)
        ).all()
        assert len(challenges) == 2
        assert challenges[0].consumed_at is not None
        assert challenges[1].consumed_at is None
        expires_at = challenges[1].expires_at.replace(tzinfo=timezone.utc)
        created_at = challenges[1].created_at.replace(tzinfo=timezone.utc)
        assert timedelta(minutes=4, seconds=59) <= expires_at - created_at <= timedelta(minutes=5, seconds=1)
        assert "otp" not in {column.name.lower() for column in OtpChallenge.__table__.columns if "code" in column.name.lower()}


def test_correct_otp_registers_customer(client: TestClient, database_engine) -> None:
    assert request_otp(client).status_code == 200
    response = client.post("/customers/register", json=registration_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["error"] is None
    assert body["data"]["first_name"] == "Uğur"
    assert body["data"]["last_name"] == "Berktaş"
    assert body["data"]["gsm"] == "+905000000001"
    assert body["data"]["email"] == "mail@example.com"
    assert body["data"]["role"] == "CUSTOMER"
    assert "password_hash" not in response.text

    with Session(database_engine) as session:
        user = session.scalar(select(User))
        challenge = session.scalar(select(OtpChallenge))
        assert user is not None
        assert user.role == UserRole.CUSTOMER
        assert user.password_hash is None
        assert challenge is not None and challenge.consumed_at is not None


def test_email_is_optional(client: TestClient) -> None:
    request_otp(client)
    response = client.post(
        "/customers/register", json=registration_payload(email=None)
    )
    assert response.status_code == 201
    assert response.json()["data"]["email"] is None


def test_wrong_otp_increments_failed_attempts(client: TestClient, database_engine) -> None:
    request_otp(client)
    payload = registration_payload()
    payload["otp_code"] = "9999"
    response = client.post("/customers/register", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_INVALID"
    with Session(database_engine) as session:
        challenge = session.scalar(select(OtpChallenge))
        assert challenge is not None
        assert challenge.failed_attempts == 1
        assert challenge.consumed_at is None


def test_challenge_is_rejected_after_five_wrong_attempts(
    client: TestClient, database_engine
) -> None:
    request_otp(client)
    payload = registration_payload()
    payload["otp_code"] = "9999"

    for _ in range(5):
        response = client.post("/customers/register", json=payload)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "OTP_INVALID"

    payload["otp_code"] = "1234"
    response = client.post("/customers/register", json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_INVALID"

    with Session(database_engine) as session:
        challenge = session.scalar(select(OtpChallenge))
        assert challenge is not None
        assert challenge.failed_attempts == 5
        assert challenge.consumed_at is not None
        assert session.scalar(select(User)) is None


def test_expired_otp_returns_otp_expired(client: TestClient, database_engine) -> None:
    request_otp(client)
    with Session(database_engine) as session:
        challenge = session.scalar(select(OtpChallenge))
        assert challenge is not None
        challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()

    response = client.post("/customers/register", json=registration_payload())
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_EXPIRED"


def test_consumed_otp_cannot_be_reused(client: TestClient) -> None:
    request_otp(client)
    assert client.post("/customers/register", json=registration_payload()).status_code == 201

    second_payload = registration_payload(email="other@example.com")
    response = client.post("/customers/register", json=second_payload)
    assert response.status_code == 409

    # Reuse against the same challenge is independently rejected even when
    # duplicate detection does not short-circuit first.
    second_payload["gsm"] = "+905000000001"
    response = client.post("/customers/register", json=second_payload)
    assert response.status_code == 409


def test_otp_reuse_is_invalid_when_user_was_removed(client: TestClient, database_engine) -> None:
    request_otp(client)
    assert client.post("/customers/register", json=registration_payload()).status_code == 201
    with Session(database_engine) as session:
        user = session.scalar(select(User))
        session.delete(user)
        session.commit()

    response = client.post("/customers/register", json=registration_payload())
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_INVALID"


def test_duplicate_gsm_returns_409(client: TestClient) -> None:
    request_otp(client)
    client.post("/customers/register", json=registration_payload())
    response = client.post(
        "/customers/register", json=registration_payload(email="new@example.com")
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CUSTOMER_ALREADY_EXISTS"
    assert response.json()["error"]["details"] == {}


def test_duplicate_email_returns_409(client: TestClient) -> None:
    request_otp(client)
    client.post("/customers/register", json=registration_payload())

    second_gsm = "05000000002"
    request_otp(client, second_gsm)
    response = client.post(
        "/customers/register",
        json=registration_payload(gsm=second_gsm, email="MAIL@example.com"),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CUSTOMER_ALREADY_EXISTS"


@pytest.mark.parametrize("field", ["first_name", "last_name"])
@pytest.mark.parametrize("value", ["", "   "])
def test_empty_names_return_422(client: TestClient, field: str, value: str) -> None:
    payload = registration_payload()
    payload[field] = value
    response = client.post("/customers/register", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_registration_rolls_back_user_and_otp_on_failure(
    client: TestClient, database_engine, monkeypatch
) -> None:
    request_otp(client)
    original_create = UserRepository.create_customer

    def create_then_fail(self, **kwargs):
        original_create(self, **kwargs)
        raise RuntimeError("simulated post-insert failure")

    monkeypatch.setattr(UserRepository, "create_customer", create_then_fail)
    response = client.post("/customers/register", json=registration_payload())
    assert response.status_code == 500

    with Session(database_engine) as session:
        assert session.scalar(select(User)) is None
        challenge = session.scalar(select(OtpChallenge))
        assert challenge is not None
        assert challenge.consumed_at is None

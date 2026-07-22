"""Authentication, JWT, refresh rotation, logout, /me, and Admin endpoint tests."""
from datetime import datetime, timedelta, timezone
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects import postgresql

from app.core.config import settings
from app.db.dependencies import get_db
from app.main import app
from app.models import Base, OtpChallenge, OtpPurpose, RefreshToken, User, UserRole
from app.schemas.staff import StaffCreate, StaffRole
from app.security.passwords import hash_password
from app.security.tokens import create_access_token, hash_refresh_token
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.services.otp_service import OtpService
from app.services.staff_service import StaffService


TEST_JWT_SECRET = "test-only-jwt-secret-with-more-than-32-characters"
CUSTOMER_GSM = "+905551234567"


@pytest.fixture(autouse=True)
def jwt_configuration(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(settings, "jwt_issuer", "fraudcell-identity")
    monkeypatch.setattr(settings, "jwt_audience", "fraudcell-platform")
    monkeypatch.setattr(settings, "access_token_expire_minutes", 15)
    monkeypatch.setattr(settings, "refresh_token_expire_days", 7)


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


def create_customer(
    engine, *, gsm: str = CUSTOMER_GSM, email: str = "customer@example.com", active=True
) -> uuid.UUID:
    with Session(engine) as session:
        user = User(
            first_name="Customer",
            last_name="User",
            gsm=gsm,
            email=email,
            password_hash=None,
            role=UserRole.CUSTOMER,
            is_active=active,
        )
        session.add(user)
        session.commit()
        return user.id


def create_staff(
    engine,
    *,
    email: str = "admin@example.com",
    role: StaffRole = StaffRole.ADMIN,
    active: bool = True,
    password: str = "Strong1!Password",
) -> uuid.UUID:
    with Session(engine) as session:
        response = StaffService(session).create_staff(
            StaffCreate(
                first_name="Staff",
                last_name="User",
                email=email,
                password=password,
                role=role,
                specializations=["Fraud"] if role == StaffRole.ANALYST else [],
                regions=["TR"] if role == StaffRole.ANALYST else [],
            )
        )
        user = session.get(User, response.id)
        user.is_active = active
        session.commit()
        return response.id


def request_login_otp(client: TestClient, gsm: str = "05551234567"):
    return client.post("/customers/login/otp/request", json={"gsm": gsm})


def customer_login(client: TestClient, code: str = "1234"):
    return client.post(
        "/customers/login", json={"gsm": "05551234567", "otp_code": code}
    )


def staff_login(
    client: TestClient,
    email: str = "admin@example.com",
    password: str = "Strong1!Password",
):
    return client.post("/staff/login", json={"email": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def user_access_token(engine, user_id: uuid.UUID) -> str:
    with Session(engine) as session:
        return create_access_token(session.get(User, user_id))


def test_customer_login_otp_request_creates_login_challenge(
    client, database_engine
) -> None:
    create_customer(database_engine)
    response = request_login_otp(client)
    assert response.status_code == 200
    assert "1234" not in response.text

    with Session(database_engine) as session:
        challenge = session.scalar(select(OtpChallenge))
        assert challenge is not None
        assert challenge.purpose == OtpPurpose.LOGIN


def test_unknown_customer_gets_same_200_without_challenge(
    client, database_engine
) -> None:
    unknown_response = request_login_otp(client)
    create_customer(database_engine)
    known_response = request_login_otp(client)
    assert unknown_response.status_code == known_response.status_code == 200
    assert unknown_response.json() == known_response.json()
    with Session(database_engine) as session:
        assert session.scalar(select(func.count(OtpChallenge.id))) == 1


def test_registration_challenge_cannot_be_used_for_login(
    client, database_engine
) -> None:
    create_customer(database_engine)
    with Session(database_engine) as session:
        OtpService(session).request_challenge(CUSTOMER_GSM, OtpPurpose.REGISTER)
    response = customer_login(client)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_INVALID"


def test_customer_login_issues_tokens_and_consumes_otp(
    client, database_engine
) -> None:
    create_customer(database_engine)
    request_login_otp(client)
    response = customer_login(client)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 900
    assert data["user"]["role"] == "CUSTOMER"
    assert "password_hash" not in response.text

    with Session(database_engine) as session:
        challenge = session.scalar(select(OtpChallenge))
        refresh = session.scalar(select(RefreshToken))
        assert challenge.consumed_at is not None
        assert refresh.token_hash == hash_refresh_token(data["refresh_token"])
        assert data["refresh_token"] not in refresh.token_hash


def test_customer_otp_reuse_is_rejected(client, database_engine) -> None:
    create_customer(database_engine)
    request_login_otp(client)
    assert customer_login(client).status_code == 200
    response = customer_login(client)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_INVALID"


def test_customer_wrong_and_expired_otp(client, database_engine) -> None:
    create_customer(database_engine)
    request_login_otp(client)
    wrong = customer_login(client, "9999")
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "OTP_INVALID"
    with Session(database_engine) as session:
        challenge = session.scalar(select(OtpChallenge))
        assert challenge.failed_attempts == 1
        challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    expired = customer_login(client)
    assert expired.status_code == 400
    assert expired.json()["error"]["code"] == "OTP_EXPIRED"


def test_inactive_or_unknown_customer_authentication_fails(
    client, database_engine
) -> None:
    create_customer(database_engine, active=False)
    response = customer_login(client)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_staff_login_with_normalized_email(client, database_engine) -> None:
    create_staff(database_engine)
    response = staff_login(client, email=" ADMIN@EXAMPLE.COM ")
    assert response.status_code == 200
    assert response.json()["data"]["user"]["role"] == "ADMIN"


def test_wrong_staff_email_and_password_have_identical_error(
    client, database_engine
) -> None:
    create_staff(database_engine)
    wrong_email = staff_login(client, email="missing@example.com")
    wrong_password = staff_login(client, password="Wrong1!Password")
    assert wrong_email.status_code == wrong_password.status_code == 401
    assert wrong_email.json() == wrong_password.json()
    assert wrong_email.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_customer_and_inactive_user_cannot_staff_login(client, database_engine) -> None:
    create_customer(database_engine)
    create_staff(database_engine, email="inactive@example.com", active=False)
    customer_response = staff_login(
        client, email="customer@example.com", password="Strong1!Password"
    )
    inactive_response = staff_login(client, email="inactive@example.com")
    assert customer_response.status_code == inactive_response.status_code == 401
    assert customer_response.json() == inactive_response.json()


def test_access_token_has_required_claims_and_fifteen_minute_lifetime(
    database_engine,
) -> None:
    user_id = create_staff(database_engine)
    token = user_access_token(database_engine, user_id)
    claims = jwt.decode(
        token,
        TEST_JWT_SECRET,
        algorithms=["HS256"],
        issuer="fraudcell-identity",
        audience="fraudcell-platform",
    )
    assert claims["sub"] == claims["user_id"] == str(user_id)
    assert claims["type"] == "access"
    assert claims["role"] == "ADMIN"
    assert claims["specializations"] == []
    assert claims["regions"] == []
    assert uuid.UUID(claims["jti"])
    assert claims["exp"] - claims["iat"] == 900


def test_me_success_and_inactive_user_rejection(client, database_engine) -> None:
    user_id = create_staff(database_engine)
    token = user_access_token(database_engine, user_id)
    success = client.get("/me", headers=bearer(token))
    assert success.status_code == 200
    assert success.json()["data"]["id"] == str(user_id)

    with Session(database_engine) as session:
        session.get(User, user_id).is_active = False
        session.commit()
    rejected = client.get("/me", headers=bearer(token))
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "FORBIDDEN"


def token_with_overrides(engine, user_id, **overrides) -> str:
    with Session(engine) as session:
        valid = create_access_token(session.get(User, user_id))
    claims = jwt.decode(valid, options={"verify_signature": False})
    claims.update(overrides)
    return jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")


@pytest.mark.parametrize(
    ("kind", "expected_code"),
    [
        ("tampered", "TOKEN_INVALID"),
        ("expired", "TOKEN_EXPIRED"),
        ("issuer", "TOKEN_INVALID"),
        ("audience", "TOKEN_INVALID"),
        ("type", "TOKEN_INVALID"),
    ],
)
def test_me_rejects_invalid_tokens(
    client, database_engine, kind: str, expected_code: str
) -> None:
    user_id = create_staff(database_engine)
    if kind == "tampered":
        token = user_access_token(database_engine, user_id)
        token = token[:-1] + ("a" if token[-1] != "a" else "b")
    elif kind == "expired":
        token = token_with_overrides(
            database_engine,
            user_id,
            iat=int((datetime.now(timezone.utc) - timedelta(minutes=20)).timestamp()),
            exp=int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp()),
        )
    elif kind == "issuer":
        token = token_with_overrides(database_engine, user_id, iss="wrong")
    elif kind == "audience":
        token = token_with_overrides(database_engine, user_id, aud="wrong")
    else:
        token = token_with_overrides(database_engine, user_id, type="refresh")

    response = client.get("/me", headers=bearer(token))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == expected_code


def test_missing_authorization_and_opaque_refresh_are_rejected(
    client, database_engine
) -> None:
    create_staff(database_engine)
    login = staff_login(client).json()["data"]
    missing = client.get("/me")
    opaque = client.get("/me", headers=bearer(login["refresh_token"]))
    assert missing.status_code == opaque.status_code == 401
    assert opaque.json()["error"]["code"] == "TOKEN_INVALID"


def test_refresh_hash_expiry_and_successful_rotation(client, database_engine) -> None:
    create_staff(database_engine)
    login_data = staff_login(client).json()["data"]
    raw_old = login_data["refresh_token"]
    with Session(database_engine) as session:
        old = session.scalar(select(RefreshToken))
        expires_at = old.expires_at.replace(tzinfo=timezone.utc)
        created_at = old.created_at.replace(tzinfo=timezone.utc)
        assert old.token_hash == hash_refresh_token(raw_old)
        assert raw_old not in old.token_hash
        assert timedelta(days=6, hours=23, minutes=59) <= expires_at - created_at <= timedelta(days=7, minutes=1)

    response = client.post("/tokens/refresh", json={"refresh_token": raw_old})
    assert response.status_code == 200
    raw_new = response.json()["data"]["refresh_token"]
    assert raw_new != raw_old
    with Session(database_engine) as session:
        tokens = session.scalars(select(RefreshToken).order_by(RefreshToken.created_at)).all()
        old, new = tokens
        assert old.revoked_at is not None
        assert old.replaced_by_token_id == new.id
        assert new.revoked_at is None


def test_rotated_token_reuse_revokes_all_active_sessions(
    client, database_engine
) -> None:
    create_staff(database_engine)
    first = staff_login(client).json()["data"]["refresh_token"]
    second = staff_login(client).json()["data"]["refresh_token"]
    assert client.post("/tokens/refresh", json={"refresh_token": first}).status_code == 200

    reuse = client.post("/tokens/refresh", json={"refresh_token": first})
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "TOKEN_REUSE_DETECTED"
    with Session(database_engine) as session:
        active = session.scalar(
            select(func.count(RefreshToken.id)).where(RefreshToken.revoked_at.is_(None))
        )
        assert active == 0
        second_record = session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(second)
            )
        )
        assert second_record.revoked_at is not None


def test_unknown_refresh_does_not_affect_sessions(client, database_engine) -> None:
    create_staff(database_engine)
    staff_login(client)
    response = client.post(
        "/tokens/refresh", json={"refresh_token": "unknown-random-token"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"
    with Session(database_engine) as session:
        assert session.scalar(
            select(func.count(RefreshToken.id)).where(RefreshToken.revoked_at.is_(None))
        ) == 1


def test_expired_refresh_token_is_rejected(client, database_engine) -> None:
    create_staff(database_engine)
    raw_token = staff_login(client).json()["data"]["refresh_token"]
    with Session(database_engine) as session:
        record = session.scalar(select(RefreshToken))
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    response = client.post("/tokens/refresh", json={"refresh_token": raw_token})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


def test_refresh_lookup_uses_select_for_update() -> None:
    class CapturingSession:
        statement = None

        def scalar(self, statement):
            self.statement = statement
            return None

    session = CapturingSession()
    RefreshTokenRepository(session).get_by_hash_for_update("a" * 64)
    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql


def test_logout_is_session_scoped_and_idempotent(client, database_engine) -> None:
    create_staff(database_engine)
    first = staff_login(client).json()["data"]["refresh_token"]
    second = staff_login(client).json()["data"]["refresh_token"]
    for _ in range(2):
        response = client.post("/tokens/logout", json={"refresh_token": first})
        assert response.status_code == 200
    with Session(database_engine) as session:
        first_record = session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(first)
            )
        )
        second_record = session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(second)
            )
        )
        assert first_record.revoked_at is not None
        assert second_record.revoked_at is None


def staff_account_payload(email="new.staff@example.com") -> dict:
    return {
        "first_name": "New",
        "last_name": "Analyst",
        "email": email,
        "password": "NewStaff1!Password",
        "role": "ANALYST",
        "specializations": ["Fraud"],
        "regions": ["TR"],
        "max_active_cases": 10,
    }


def test_admin_can_create_staff_without_sensitive_response(
    client, database_engine
) -> None:
    admin_id = create_staff(database_engine)
    token = user_access_token(database_engine, admin_id)
    response = client.post(
        "/staff/accounts", json=staff_account_payload(), headers=bearer(token)
    )
    assert response.status_code == 201
    assert response.json()["data"]["role"] == "ANALYST"
    assert "password" not in response.text
    assert "password_hash" not in response.text


@pytest.mark.parametrize(
    "role", [StaffRole.ANALYST, StaffRole.SUPERVISOR, UserRole.CUSTOMER]
)
def test_non_admin_roles_cannot_create_staff(
    client, database_engine, role
) -> None:
    if role == UserRole.CUSTOMER:
        user_id = create_customer(database_engine)
    else:
        user_id = create_staff(
            database_engine, email=f"{role.value.lower()}@example.com", role=role
        )
    token = user_access_token(database_engine, user_id)
    response = client.post(
        "/staff/accounts", json=staff_account_payload(), headers=bearer(token)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_staff_creation_requires_authorization(client) -> None:
    response = client.post("/staff/accounts", json=staff_account_payload())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_INVALID"


def test_staff_validation_response_never_echoes_password(
    client, database_engine
) -> None:
    admin_id = create_staff(database_engine)
    token = user_access_token(database_engine, admin_id)
    plaintext = "weak"
    payload = staff_account_payload()
    payload["password"] = plaintext
    response = client.post("/staff/accounts", json=payload, headers=bearer(token))
    assert response.status_code == 422
    assert plaintext not in response.text

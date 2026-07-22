"""Account lockout, DB-backed RBAC, and immutable audit behavior tests."""
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.dependencies import get_db
from app.main import app
from app.models import AuditLog, Base, RefreshToken, User, UserRole
from app.repositories.user_repository import UserRepository
from app.repositories.audit_repository import AuditRepository
from app.schemas.staff import StaffCreate, StaffRole
from app.security.tokens import create_access_token
from app.security.client_ip import get_client_ip
from app.services.audit_service import (
    AuditAction,
    AuditResult,
    AuditService,
    sanitize_audit_details,
)
from app.services.auth_service import AuthService
from app.services.staff_service import StaffService


TEST_JWT_SECRET = "test-only-lock-audit-secret-more-than-32-characters"


@pytest.fixture(autouse=True)
def jwt_configuration(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(settings, "jwt_issuer", "fraudcell-identity")
    monkeypatch.setattr(settings, "jwt_audience", "fraudcell-platform")


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


def create_user(
    engine,
    *,
    email: str,
    role: UserRole,
    password: str = "Strong1!Password",
    active: bool = True,
    gsm: str | None = None,
) -> uuid.UUID:
    if role == UserRole.CUSTOMER:
        with Session(engine) as session:
            user = User(
                first_name="Customer",
                last_name="User",
                email=email,
                gsm=gsm or "+905551234567",
                role=role,
                password_hash=None,
                is_active=active,
            )
            session.add(user)
            session.commit()
            return user.id

    with Session(engine) as session:
        response = StaffService(session).create_staff(
            StaffCreate(
                first_name="Staff",
                last_name="User",
                email=email,
                password=password,
                role=StaffRole(role.value),
                specializations=["Fraud"] if role == UserRole.ANALYST else [],
                regions=["TR"] if role == UserRole.ANALYST else [],
            )
        )
        user = session.get(User, response.id)
        user.is_active = active
        session.commit()
        return user.id


def login(client: TestClient, email="admin@example.com", password="Strong1!Password"):
    return client.post("/staff/login", json={"email": email, "password": password})


def access_token(engine, user_id: uuid.UUID) -> str:
    with Session(engine) as session:
        return create_access_token(session.get(User, user_id))


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def staff_payload(email="created@example.com") -> dict:
    return {
        "first_name": "Created",
        "last_name": "Analyst",
        "email": email,
        "password": "Created1!Password",
        "role": "ANALYST",
        "specializations": ["Fraud"],
        "regions": ["TR"],
        "max_active_cases": 10,
    }


def test_first_four_failures_then_fifth_locks_with_headers(
    client, database_engine
) -> None:
    user_id = create_user(
        database_engine, email="admin@example.com", role=UserRole.ADMIN
    )
    for expected_count in range(1, 5):
        response = login(client, password="Wrong1!Password")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"
        with Session(database_engine) as session:
            assert session.get(User, user_id).failed_login_count == expected_count

    locked = login(client, password="Wrong1!Password")
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "ACCOUNT_LOCKED"
    remaining = locked.json()["error"]["details"]["remaining_seconds"]
    assert 899 <= remaining <= 900
    assert int(locked.headers["Retry-After"]) == remaining
    with Session(database_engine) as session:
        user = session.get(User, user_id)
        assert user.failed_login_count == 5
        assert user.locked_until is not None
        actions = session.scalars(select(AuditLog.action)).all()
        assert actions.count("AUTH_LOGIN_FAILED") == 5
        assert actions.count("AUTH_ACCOUNT_LOCKED") == 1


def test_locked_account_rejects_correct_password_without_changing_counter(
    client, database_engine
) -> None:
    user_id = create_user(
        database_engine, email="admin@example.com", role=UserRole.ADMIN
    )
    for _ in range(5):
        login(client, password="Wrong1!Password")
    response = login(client, password="Strong1!Password")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "ACCOUNT_LOCKED"
    with Session(database_engine) as session:
        assert session.get(User, user_id).failed_login_count == 5


def test_lock_expiry_uses_injected_clock_and_success_resets(database_engine) -> None:
    user_id = create_user(
        database_engine, email="admin@example.com", role=UserRole.ADMIN
    )
    start = datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc)
    with Session(database_engine) as session:
        service = AuthService(session, clock=lambda: start)
        for attempt in range(5):
            with pytest.raises(Exception) as exc_info:
                service.staff_login("admin@example.com", "Wrong1!Password")
            assert exc_info.value.status_code == (429 if attempt == 4 else 401)

        service = AuthService(
            session, clock=lambda: start + timedelta(minutes=15, seconds=1)
        )
        response = service.staff_login("admin@example.com", "Strong1!Password")
        assert response.user.id == user_id

    with Session(database_engine) as session:
        user = session.get(User, user_id)
        assert user.failed_login_count == 0
        assert user.locked_until is None


def test_wrong_password_after_expired_lock_starts_new_cycle(database_engine) -> None:
    user_id = create_user(
        database_engine, email="admin@example.com", role=UserRole.ADMIN
    )
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    with Session(database_engine) as session:
        user = session.get(User, user_id)
        user.failed_login_count = 5
        user.locked_until = now - timedelta(seconds=1)
        session.commit()
        with pytest.raises(Exception) as exc_info:
            AuthService(session, clock=lambda: now).staff_login(
                "admin@example.com", "Wrong1!Password"
            )
        assert exc_info.value.status_code == 401
    with Session(database_engine) as session:
        user = session.get(User, user_id)
        assert user.failed_login_count == 1
        assert user.locked_until is None


def test_unknown_email_matches_wrong_password_response(client, database_engine) -> None:
    create_user(database_engine, email="admin@example.com", role=UserRole.ADMIN)
    missing = login(client, email="missing@example.com", password="Wrong1!Password")
    wrong = login(client, password="Wrong1!Password")
    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == wrong.json()


def test_staff_lock_lookup_uses_select_for_update() -> None:
    class CapturingSession:
        statement = None

        def scalar(self, statement):
            self.statement = statement
            return None

    session = CapturingSession()
    UserRepository(session).get_by_email_for_update("admin@example.com")
    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql


def test_locked_account_does_not_verify_password(database_engine, monkeypatch) -> None:
    user_id = create_user(
        database_engine, email="admin@example.com", role=UserRole.ADMIN
    )
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    with Session(database_engine) as session:
        user = session.get(User, user_id)
        user.failed_login_count = 5
        user.locked_until = now + timedelta(minutes=10)
        session.commit()

        def must_not_run(*_args, **_kwargs):
            raise AssertionError("password verification must not run while locked")

        monkeypatch.setattr("app.services.auth_service.verify_password", must_not_run)
        with pytest.raises(Exception) as exc_info:
            AuthService(session, clock=lambda: now).staff_login(
                "admin@example.com", "Strong1!Password"
            )
        assert exc_info.value.code == "ACCOUNT_LOCKED"


def test_db_role_is_authoritative_and_denial_is_audited(
    client, database_engine
) -> None:
    user_id = create_user(
        database_engine, email="admin@example.com", role=UserRole.ADMIN
    )
    token = access_token(database_engine, user_id)
    with Session(database_engine) as session:
        session.get(User, user_id).role = UserRole.ANALYST
        session.commit()

    response = client.post(
        "/staff/accounts", json=staff_payload(), headers=auth_header(token)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    with Session(database_engine) as session:
        audit = session.scalar(
            select(AuditLog).where(AuditLog.action == "ACCESS_DENIED")
        )
        assert audit.actor_user_id == user_id
        assert audit.details["actual_role"] == "ANALYST"
        assert "authorization" not in str(audit.details).lower()


def test_inactive_user_is_403_and_audited(client, database_engine) -> None:
    user_id = create_user(
        database_engine, email="admin@example.com", role=UserRole.ADMIN
    )
    token = access_token(database_engine, user_id)
    with Session(database_engine) as session:
        session.get(User, user_id).is_active = False
        session.commit()
    response = client.get("/me", headers=auth_header(token))
    assert response.status_code == 403
    with Session(database_engine) as session:
        audit = session.scalar(select(AuditLog))
        assert audit.action == "ACCESS_DENIED"
        assert audit.details["reason"] == "INACTIVE_USER"


@pytest.mark.parametrize(
    "role", [UserRole.ANALYST, UserRole.SUPERVISOR, UserRole.CUSTOMER]
)
def test_only_admin_can_read_audits_and_denials_do_not_recurse(
    client, database_engine, role
) -> None:
    user_id = create_user(
        database_engine,
        email=f"{role.value.lower()}@example.com",
        role=role,
    )
    token = access_token(database_engine, user_id)
    response = client.get("/audit-logs", headers=auth_header(token))
    assert response.status_code == 403
    with Session(database_engine) as session:
        records = session.scalars(select(AuditLog)).all()
        assert len(records) == 1
        assert records[0].action == "ACCESS_DENIED"


def test_admin_audit_listing_pagination_filter_and_newest_first(
    client, database_engine
) -> None:
    admin_id = create_user(
        database_engine, email="admin@example.com", role=UserRole.ADMIN
    )
    with Session(database_engine) as session:
        audit = AuditService(session)
        first = audit.record(
            actor_user_id=admin_id,
            action=AuditAction.AUTH_LOGIN_FAILED,
            result=AuditResult.FAILURE,
        )
        second = audit.record(
            actor_user_id=admin_id,
            action=AuditAction.AUTH_LOGIN_SUCCESS,
            result=AuditResult.SUCCESS,
        )
        first.created_at = datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc)
        second.created_at = datetime(2026, 7, 23, 11, 0, tzinfo=timezone.utc)
        session.commit()

    token = access_token(database_engine, admin_id)
    response = client.get(
        "/audit-logs?page=1&page_size=1&result=SUCCESS",
        headers=auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert data["total"] == 1
    assert data["items"][0]["action"] == "AUTH_LOGIN_SUCCESS"

    all_items = client.get("/audit-logs", headers=auth_header(token)).json()["data"]["items"]
    assert all_items[0]["action"] == "AUTH_LOGIN_SUCCESS"


def test_login_customer_token_and_staff_creation_actions_are_audited(
    client, database_engine
) -> None:
    admin_id = create_user(
        database_engine, email="admin@example.com", role=UserRole.ADMIN
    )

    failed = login(client, password="Wrong1!Password")
    assert failed.status_code == 401
    successful = login(client)
    assert successful.status_code == 200
    admin_access = successful.json()["data"]["access_token"]
    old_refresh = successful.json()["data"]["refresh_token"]

    created = client.post(
        "/staff/accounts",
        json=staff_payload(),
        headers=auth_header(admin_access),
    )
    assert created.status_code == 201
    created_id = created.json()["data"]["id"]

    rotation = client.post(
        "/tokens/refresh", json={"refresh_token": old_refresh}
    )
    assert rotation.status_code == 200
    new_refresh = rotation.json()["data"]["refresh_token"]
    logout = client.post("/tokens/logout", json={"refresh_token": new_refresh})
    assert logout.status_code == 200
    reuse = client.post("/tokens/refresh", json={"refresh_token": old_refresh})
    assert reuse.status_code == 401

    customer_id = create_user(
        database_engine,
        email="customer@example.com",
        role=UserRole.CUSTOMER,
        gsm="+905551234567",
    )
    client.post("/customers/login/otp/request", json={"gsm": "05551234567"})
    wrong_otp = client.post(
        "/customers/login", json={"gsm": "05551234567", "otp_code": "9999"}
    )
    assert wrong_otp.status_code == 400
    good_otp = client.post(
        "/customers/login", json={"gsm": "05551234567", "otp_code": "1234"}
    )
    assert good_otp.status_code == 200

    with Session(database_engine) as session:
        records = session.scalars(select(AuditLog)).all()
        actions = [record.action for record in records]
        assert "AUTH_LOGIN_FAILED" in actions
        assert "AUTH_LOGIN_SUCCESS" in actions
        assert "AUTH_TOKEN_REFRESHED" in actions
        assert "AUTH_TOKEN_REUSE_DETECTED" in actions
        assert "AUTH_LOGOUT" in actions
        assert "STAFF_ACCOUNT_CREATED" in actions
        staff_record = next(
            record for record in records if record.action == "STAFF_ACCOUNT_CREATED"
        )
        assert staff_record.actor_user_id == admin_id
        assert staff_record.resource_id == created_id
        customer_records = [
            record for record in records if record.actor_user_id == customer_id
        ]
        assert {record.action for record in customer_records} >= {
            "AUTH_LOGIN_FAILED",
            "AUTH_LOGIN_SUCCESS",
        }


def test_audit_write_failure_does_not_bypass_lock_counter(
    client, database_engine, monkeypatch
) -> None:
    user_id = create_user(
        database_engine, email="admin@example.com", role=UserRole.ADMIN
    )

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("simulated audit storage failure")

    monkeypatch.setattr(AuditRepository, "create", fail_audit)
    response = login(client, password="Wrong1!Password")
    assert response.status_code == 401
    with Session(database_engine) as session:
        assert session.get(User, user_id).failed_login_count == 1


def test_sensitive_details_are_recursively_removed(database_engine) -> None:
    details = {
        "Password": "plain",
        "safe": {
            "OTP_CODE": "1234",
            "nested": [{"Authorization": "Bearer token", "reason": "test"}],
        },
        "REFRESH-TOKEN": "raw",
    }
    sanitized = sanitize_audit_details(details)
    serialized = str(sanitized).lower()
    assert "plain" not in serialized
    assert "1234" not in serialized
    assert "bearer" not in serialized
    assert "raw" not in serialized
    assert sanitized["safe"]["nested"][0]["reason"] == "test"

    with Session(database_engine) as session:
        AuditService(session).record(
            action=AuditAction.AUTH_LOGIN_FAILED,
            result=AuditResult.FAILURE,
            details=details,
        )
        session.commit()
    with Session(database_engine) as session:
        assert session.scalar(select(AuditLog)).details == sanitized


def test_audit_endpoint_sanitizes_legacy_sensitive_details(
    client, database_engine
) -> None:
    admin_id = create_user(
        database_engine, email="admin@example.com", role=UserRole.ADMIN
    )
    with Session(database_engine) as session:
        session.add(
            AuditLog(
                actor_user_id=admin_id,
                action="AUTH_LOGIN_FAILED",
                result="FAILURE",
                details={"Password": "must-not-return", "reason": "test"},
            )
        )
        session.commit()
    response = client.get(
        "/audit-logs", headers=auth_header(access_token(database_engine, admin_id))
    )
    assert response.status_code == 200
    details = response.json()["data"]["items"][0]["details"]
    assert details == {"reason": "test"}
    assert "must-not-return" not in response.text


def test_role_change_helper_is_safe(database_engine) -> None:
    actor_id = create_user(
        database_engine, email="admin@example.com", role=UserRole.ADMIN
    )
    target_id = create_user(
        database_engine, email="analyst@example.com", role=UserRole.ANALYST
    )
    with Session(database_engine) as session:
        AuditService(session).audit_role_change(
            actor_user_id=actor_id,
            target_user_id=target_id,
            old_role="ANALYST",
            new_role="SUPERVISOR",
        )
        session.commit()
    with Session(database_engine) as session:
        record = session.scalar(select(AuditLog))
        assert record.action == "ROLE_CHANGED"
        assert record.resource_id == str(target_id)
        assert record.details == {
            "old_role": "ANALYST",
            "new_role": "SUPERVISOR",
        }


def test_no_audit_update_or_delete_endpoints(client) -> None:
    random_id = str(uuid.uuid4())
    assert client.patch(f"/audit-logs/{random_id}", json={}).status_code == 404
    assert client.delete(f"/audit-logs/{random_id}").status_code == 404


def test_forwarded_ip_is_only_used_for_trusted_proxy() -> None:
    from starlette.requests import Request

    trusted_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/me",
            "headers": [(b"x-forwarded-for", b"203.0.113.10, 172.20.0.2")],
            "client": ("172.20.0.5", 1234),
            "server": ("identity-service", 8000),
            "scheme": "http",
            "query_string": b"",
        }
    )
    untrusted_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/me",
            "headers": [(b"x-forwarded-for", b"198.51.100.99")],
            "client": ("8.8.8.8", 1234),
            "server": ("identity-service", 8000),
            "scheme": "http",
            "query_string": b"",
        }
    )
    assert get_client_ip(trusted_request) == "203.0.113.10"
    assert get_client_ip(untrusted_request) == "8.8.8.8"

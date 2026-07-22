"""Tests for the explicit, idempotent Admin bootstrap CLI."""
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cli import bootstrap_admin
from app.models import Base, StaffProfile, User, UserRole
from app.schemas.staff import StaffCreate, StaffRole
from app.services.staff_service import StaffService


ENVIRONMENT = {
    "BOOTSTRAP_ADMIN_FIRST_NAME": " Initial ",
    "BOOTSTRAP_ADMIN_LAST_NAME": " Admin ",
    "BOOTSTRAP_ADMIN_EMAIL": " Bootstrap.Admin@Example.COM ",
    "BOOTSTRAP_ADMIN_PASSWORD": "Bootstrap9!Secret",
}


@pytest.fixture()
def database_engine(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(bootstrap_admin, "_get_engine", lambda: engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def set_bootstrap_environment(monkeypatch, **overrides) -> None:
    values = ENVIRONMENT | overrides
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def clear_bootstrap_environment(monkeypatch) -> None:
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


def test_missing_environment_variable_exits_one(monkeypatch, capsys) -> None:
    clear_bootstrap_environment(monkeypatch)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")

    assert bootstrap_admin.main() == 1
    captured = capsys.readouterr()
    assert "Missing required environment variables" in captured.err
    assert "BOOTSTRAP_ADMIN_PASSWORD" in captured.err


def test_invalid_password_exits_one_without_leaking_password(
    monkeypatch, capsys
) -> None:
    clear_bootstrap_environment(monkeypatch)
    unsafe_password = "weak"
    set_bootstrap_environment(
        monkeypatch, BOOTSTRAP_ADMIN_PASSWORD=unsafe_password
    )

    assert bootstrap_admin.main() == 1
    captured = capsys.readouterr()
    assert "Password policy failed" in captured.err
    assert "PASSWORD_TOO_SHORT" in captured.err
    assert unsafe_password not in captured.out + captured.err


def test_validation_error_reports_field_without_leaking_password(
    monkeypatch, capsys
) -> None:
    clear_bootstrap_environment(monkeypatch)
    secret_password = "Bootstrap9!Secret"
    set_bootstrap_environment(
        monkeypatch,
        BOOTSTRAP_ADMIN_EMAIL="not-an-email",
        BOOTSTRAP_ADMIN_PASSWORD=secret_password,
    )

    assert bootstrap_admin.main() == 1
    captured = capsys.readouterr()
    assert "Invalid bootstrap Admin configuration" in captured.err
    assert "email:" in captured.err
    assert "valid email address" in captured.err
    assert secret_password not in captured.out + captured.err


def test_admin_bootstrap_is_idempotent_and_does_not_leak_secrets(
    database_engine, monkeypatch, capsys
) -> None:
    clear_bootstrap_environment(monkeypatch)
    set_bootstrap_environment(monkeypatch)

    assert bootstrap_admin.main() == 0
    first_output = capsys.readouterr()
    assert "bootstrap.admin@example.com" in first_output.out
    assert "created" in first_output.out

    assert bootstrap_admin.main() == 0
    second_output = capsys.readouterr()
    assert "already existed" in second_output.out

    with Session(database_engine) as session:
        assert session.scalar(select(func.count(User.id))) == 1
        user = session.scalar(select(User))
        assert user is not None
        assert user.role == UserRole.ADMIN
        assert user.gsm is None
        assert user.password_hash is not None
        profile = session.scalar(select(StaffProfile))
        assert profile is not None
        assert profile.specializations == []
        assert profile.regions == []
        assert profile.max_active_cases == 10
        output = first_output.out + first_output.err + second_output.out + second_output.err
        assert ENVIRONMENT["BOOTSTRAP_ADMIN_PASSWORD"] not in output
        assert user.password_hash not in output


def test_existing_non_admin_email_exits_one(
    database_engine, monkeypatch, capsys
) -> None:
    with Session(database_engine) as session:
        StaffService(session).create_staff(
            StaffCreate(
                first_name="Existing",
                last_name="Supervisor",
                email="bootstrap.admin@example.com",
                password="Existing9!Secret",
                role=StaffRole.SUPERVISOR,
            )
        )

    clear_bootstrap_environment(monkeypatch)
    set_bootstrap_environment(monkeypatch)
    assert bootstrap_admin.main() == 1
    captured = capsys.readouterr()
    assert "BOOTSTRAP_ADMIN_ROLE_CONFLICT" in captured.err
    assert ENVIRONMENT["BOOTSTRAP_ADMIN_PASSWORD"] not in captured.out + captured.err

    with Session(database_engine) as session:
        assert session.scalar(select(func.count(User.id))) == 1

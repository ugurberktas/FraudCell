import uuid

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cli import demo_user_info, seed_demo_users
from app.common.exceptions import AppException
from app.db.base import Base
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.security.passwords import verify_password


@pytest.fixture
def database_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def demo_env(monkeypatch):
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "DemoAdmin1!")
    monkeypatch.setenv("DEMO_SUPERVISOR_PASSWORD", "DemoSupervisor1!")
    monkeypatch.setenv("DEMO_ANALYST_PASSWORD", "DemoAnalyst1!")
    monkeypatch.setenv("DEMO_CUSTOMER_GSM", "05550000001")
    monkeypatch.setenv("DEMO_OTP_CODE", "1234")


def test_demo_user_seed_is_idempotent(database_session, demo_env):
    first = seed_demo_users.seed(database_session)
    first_hashes = {
        user.email: user.password_hash
        for user in database_session.scalars(
            select(User).where(User.role != UserRole.CUSTOMER)
        )
    }
    second = seed_demo_users.seed(database_session)
    second_hashes = {
        user.email: user.password_hash
        for user in database_session.scalars(
            select(User).where(User.role != UserRole.CUSTOMER)
        )
    }
    assert first == second
    assert first_hashes == second_hashes
    assert database_session.scalar(select(func.count()).select_from(User)) == 6
    assert second["customer"]["gsm"] == "+905550000001"
    assert demo_user_info.lookup(database_session) == second


def test_demo_seed_aligns_existing_staff_password_with_environment(
    database_session, demo_env, monkeypatch
):
    first = seed_demo_users.seed(database_session)
    supervisor_email = "demo.supervisor@fraudcell.com"
    supervisor = database_session.scalar(
        select(User).where(User.email == supervisor_email)
    )
    original_hash = supervisor.password_hash

    replacement_password = "ReplacementSupervisor2!"
    monkeypatch.setenv("DEMO_SUPERVISOR_PASSWORD", replacement_password)
    second = seed_demo_users.seed(database_session)

    database_session.refresh(supervisor)
    assert second == first
    assert supervisor.password_hash != original_hash
    assert verify_password(replacement_password, supervisor.password_hash)
    assert not verify_password("DemoSupervisor1!", supervisor.password_hash)
    aligned_hash = supervisor.password_hash

    assert seed_demo_users.seed(database_session) == first
    database_session.refresh(supervisor)
    assert supervisor.password_hash == aligned_hash


def test_demo_seed_check_rejects_password_mismatch_without_mutation(
    database_session, demo_env, monkeypatch
):
    seed_demo_users.seed(database_session)
    supervisor = database_session.scalar(
        select(User).where(User.email == "demo.supervisor@fraudcell.com")
    )
    original_hash = supervisor.password_hash
    configured_password = "ConfiguredSupervisor2!"
    monkeypatch.setenv("DEMO_SUPERVISOR_PASSWORD", configured_password)

    with pytest.raises(AppException) as exc:
        seed_demo_users.seed(database_session, create_missing=False)

    assert exc.value.code == "DEMO_USER_PASSWORD_MISMATCH"
    assert configured_password not in str(exc.value)
    database_session.refresh(supervisor)
    assert supervisor.password_hash == original_hash


def test_demo_seed_rejects_role_or_profile_conflict(database_session, demo_env):
    user = User(
        id=uuid.uuid4(), first_name="Wrong", last_name="Role",
        email="demo.admin@fraudcell.com", role=UserRole.CUSTOMER,
    )
    database_session.add(user)
    database_session.commit()
    with pytest.raises(AppException) as exc:
        seed_demo_users.seed(database_session)
    assert exc.value.code == "DEMO_USER_PROFILE_CONFLICT"


def test_demo_seed_requires_password_environment(database_session, monkeypatch):
    for name in ("DEMO_ADMIN_PASSWORD", "DEMO_SUPERVISOR_PASSWORD", "DEMO_ANALYST_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="Missing required"):
        seed_demo_users.seed(database_session)

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
    second = seed_demo_users.seed(database_session)
    assert first == second
    assert database_session.scalar(select(func.count()).select_from(User)) == 6
    assert second["customer"]["gsm"] == "+905550000001"
    assert demo_user_info.lookup(database_session) == second


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

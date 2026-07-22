"""Tests for staff schemas and transactional staff creation."""
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.common.exceptions import AppException
from app.models import Base, StaffProfile, User, UserRole
from app.repositories.staff_repository import StaffRepository
from app.schemas.staff import StaffCreate, StaffRole
from app.security.passwords import verify_password
from app.services.staff_service import StaffService


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


def staff_request(
    *,
    email: str = " Staff@Example.COM ",
    role: StaffRole | str = StaffRole.ANALYST,
    specializations: list[str] | None = None,
    regions: list[str] | None = None,
) -> StaffCreate:
    return StaffCreate(
        first_name=" Ada ",
        last_name=" Lovelace ",
        email=email,
        password="Strong1!Password",
        role=role,
        specializations=(
            [" Fraud ", "Fraud", "Account Takeover"]
            if specializations is None
            else specializations
        ),
        regions=[" TR ", "TR", "EU"] if regions is None else regions,
    )


def test_staff_email_and_lists_are_normalized() -> None:
    request = staff_request()
    assert request.email == "staff@example.com"
    assert request.first_name == "Ada"
    assert request.last_name == "Lovelace"
    assert request.specializations == ["Fraud", "Account Takeover"]
    assert request.regions == ["TR", "EU"]


def test_analyst_is_created_with_profile(database_engine) -> None:
    with Session(database_engine) as session:
        response = StaffService(session).create_staff(staff_request())

    assert response.role == StaffRole.ANALYST
    assert response.specializations == ["Fraud", "Account Takeover"]
    assert response.regions == ["TR", "EU"]
    assert response.max_active_cases == 10

    with Session(database_engine) as session:
        user = session.scalar(select(User))
        profile = session.scalar(select(StaffProfile))
        assert user is not None and profile is not None
        assert user.staff_profile.id == profile.id
        assert profile.user_id == user.id
        assert user.gsm is None
        assert user.password_hash is not None
        assert verify_password("Strong1!Password", user.password_hash)


def test_analyst_requires_specialization() -> None:
    with pytest.raises(ValidationError, match="ANALYST_SPECIALIZATION_REQUIRED"):
        staff_request(specializations=[])


def test_analyst_requires_region() -> None:
    with pytest.raises(ValidationError, match="ANALYST_REGION_REQUIRED"):
        staff_request(regions=[])


@pytest.mark.parametrize("role", [StaffRole.SUPERVISOR, StaffRole.ADMIN])
def test_supervisor_and_admin_can_be_created_without_assignment_lists(
    database_engine, role: StaffRole
) -> None:
    request = staff_request(role=role, specializations=[], regions=[])
    with Session(database_engine) as session:
        response = StaffService(session).create_staff(request)
    assert response.role == role
    assert response.specializations == []
    assert response.regions == []


def test_customer_role_is_rejected() -> None:
    with pytest.raises(ValidationError):
        staff_request(role=UserRole.CUSTOMER)


def test_empty_list_values_are_rejected() -> None:
    with pytest.raises(ValidationError, match="List values must not be empty"):
        staff_request(specializations=["Fraud", "  "])


def test_max_active_cases_must_be_positive() -> None:
    data = staff_request().model_dump()
    data["max_active_cases"] = 0
    with pytest.raises(ValidationError):
        StaffCreate.model_validate(data)


def test_duplicate_email_becomes_409_domain_error(database_engine) -> None:
    with Session(database_engine) as session:
        service = StaffService(session)
        service.create_staff(staff_request())
        with pytest.raises(AppException) as exc_info:
            service.create_staff(
                staff_request(email="STAFF@example.com", role=StaffRole.ADMIN)
            )

    assert exc_info.value.code == "STAFF_ALREADY_EXISTS"
    assert exc_info.value.status_code == 409
    assert exc_info.value.details == {}


def test_staff_response_excludes_sensitive_internal_fields(database_engine) -> None:
    with Session(database_engine) as session:
        response = StaffService(session).create_staff(staff_request())
        response_fields = response.model_dump().keys()

    assert "password" not in response_fields
    assert "password_hash" not in response_fields
    assert "failed_login_count" not in response_fields
    assert "locked_until" not in response_fields


def test_staff_creation_rolls_back_on_failure(
    database_engine, monkeypatch
) -> None:
    original_create = StaffRepository.create_staff

    def create_then_fail(self, **kwargs):
        original_create(self, **kwargs)
        raise RuntimeError("simulated post-insert failure")

    monkeypatch.setattr(StaffRepository, "create_staff", create_then_fail)
    with Session(database_engine) as session:
        with pytest.raises(RuntimeError, match="simulated post-insert failure"):
            StaffService(session).create_staff(staff_request())

    with Session(database_engine) as session:
        assert session.scalar(select(func.count(User.id))) == 0
        assert session.scalar(select(func.count(StaffProfile.id))) == 0

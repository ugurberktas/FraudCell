"""Tests for Identity Service models, metadata, relationships, and migration presence."""
from pathlib import Path
from sqlalchemy import JSON, UniqueConstraint
from pydantic import ValidationError
import pytest
from app.core.config import Settings
from app.models import AuditLog, Base, OtpChallenge, OtpPurpose, RefreshToken, StaffProfile, User, UserRole


def test_expected_tables_in_metadata() -> None:
    expected_tables = {
        "users",
        "staff_profiles",
        "refresh_tokens",
        "otp_challenges",
        "audit_logs",
    }
    actual_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(actual_tables)


def test_user_role_enum_values() -> None:
    assert UserRole.CUSTOMER == "CUSTOMER"
    assert UserRole.ANALYST == "ANALYST"
    assert UserRole.SUPERVISOR == "SUPERVISOR"
    assert UserRole.ADMIN == "ADMIN"
    assert len(UserRole) == 4


def test_user_unique_constraints() -> None:
    user_table = Base.metadata.tables["users"]
    constraints = [c for c in user_table.constraints if isinstance(c, UniqueConstraint)]
    constraint_names = {c.name for c in constraints}
    assert "uq_users_gsm" in constraint_names
    assert "uq_users_email" in constraint_names
    assert user_table.columns["gsm"].unique is True or user_table.columns["gsm"].index is True
    assert user_table.columns["email"].unique is True or user_table.columns["email"].index is True


def test_staff_profile_one_to_one_relationship() -> None:
    staff_profile_table = Base.metadata.tables["staff_profiles"]
    user_id_col = staff_profile_table.columns["user_id"]
    assert user_id_col.unique is True
    
    # Check SQLAlchemy relationship definition
    user_rel = User.staff_profile.property
    assert user_rel.uselist is False


def test_refresh_token_user_relationship() -> None:
    refresh_token_rel = User.refresh_tokens.property
    assert refresh_token_rel.uselist is True
    
    token_user_rel = RefreshToken.user.property
    assert token_user_rel.mapper.class_ == User


def test_audit_log_details_is_json() -> None:
    audit_log_table = Base.metadata.tables["audit_logs"]
    details_col = audit_log_table.columns["details"]
    assert isinstance(details_col.type, JSON)


def test_alembic_migration_file_exists() -> None:
    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "001_initial_identity_schema.py"
    )
    assert migration_path.exists()
    assert migration_path.is_file()


def test_user_names_are_required_by_model() -> None:
    user_table = Base.metadata.tables["users"]
    assert user_table.columns["first_name"].nullable is False
    assert user_table.columns["last_name"].nullable is False


def test_user_name_not_null_migration_has_upgrade_and_downgrade() -> None:
    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "002_require_user_names.py"
    )
    source = migration_path.read_text(encoding="utf-8")
    assert 'down_revision: Union[str, None] = "001_initial_identity_schema"' in source
    assert "def upgrade()" in source
    assert "def downgrade()" in source
    assert source.count("nullable=False") == 2
    assert source.count("nullable=True") == 2


def test_auth_foundation_metadata_and_migration() -> None:
    otp_table = Base.metadata.tables["otp_challenges"]
    refresh_table = Base.metadata.tables["refresh_tokens"]
    assert "purpose" in otp_table.columns
    assert OtpPurpose.REGISTER == "REGISTER"
    assert OtpPurpose.LOGIN == "LOGIN"
    assert refresh_table.columns["token_hash"].unique is True

    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "003_auth_token_foundation.py"
    )
    source = migration_path.read_text(encoding="utf-8")
    assert 'down_revision: Union[str, None] = "002_require_user_names"' in source
    assert "def upgrade()" in source
    assert "def downgrade()" in source
    assert 'server_default="REGISTER"' in source
    assert "unique=True" in source


def test_production_rejects_unsafe_jwt_secret() -> None:
    for unsafe_secret in ("short", "CHANGE_ME_WITH_A_RANDOM_32_PLUS_CHARACTER_SECRET"):
        with pytest.raises(ValidationError, match="JWT_SECRET"):
            Settings(environment="production", jwt_secret=unsafe_secret)

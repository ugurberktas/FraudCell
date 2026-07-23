"""Idempotently create the fixed FraudCell demo users through domain services."""
from __future__ import annotations

import json
import argparse
import os
import sys

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.db.session import _get_engine
from app.models.user import UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.customer import CustomerRegisterRequest, normalize_turkish_gsm
from app.schemas.staff import StaffCreate, StaffRole
from app.security.passwords import (
    PasswordPolicyError,
    hash_password,
    password_needs_rehash,
    validate_password_policy,
    verify_password,
)
from app.services.customer_service import CustomerService
from app.services.otp_service import OtpService
from app.services.staff_service import StaffService


DEMO_STAFF = (
    ("Demo", "Admin", "demo.admin@fraudcell.com", StaffRole.ADMIN, [], [], "DEMO_ADMIN_PASSWORD"),
    ("Demo", "Supervisor", "demo.supervisor@fraudcell.com", StaffRole.SUPERVISOR, [], [], "DEMO_SUPERVISOR_PASSWORD"),
    ("Demo", "Kart Analisti", "demo.analyst.card@fraudcell.com", StaffRole.ANALYST, ["CALINTI_KART"], ["TR", "EU"], "DEMO_ANALYST_PASSWORD"),
    ("Demo", "Hesap Analisti", "demo.analyst.account@fraudcell.com", StaffRole.ANALYST, ["HESAP_ELE_GECIRME"], ["TR", "EU"], "DEMO_ANALYST_PASSWORD"),
    ("Demo", "AML Analisti", "demo.analyst.aml@fraudcell.com", StaffRole.ANALYST, ["PARA_AKLAMA"], ["TR", "EU", "GLOBAL"], "DEMO_ANALYST_PASSWORD"),
)


def _required_environment() -> dict[str, str]:
    names = ("DEMO_ADMIN_PASSWORD", "DEMO_SUPERVISOR_PASSWORD", "DEMO_ANALYST_PASSWORD")
    values = {name: os.getenv(name, "") for name in names}
    missing = [name for name, value in values.items() if not value.strip()]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    for name, value in values.items():
        try:
            validate_password_policy(value)
        except PasswordPolicyError as exc:
            raise ValueError(f"{name} password policy failed: {', '.join(exc.violations)}") from exc
    return values


def _validate_existing_staff(user, request: StaffCreate) -> None:
    profile = user.staff_profile
    expected_role = UserRole(request.role.value)
    if (
        user.role is not expected_role
        or profile is None
        or profile.specializations != request.specializations
        or profile.regions != request.regions
        or profile.max_active_cases != request.max_active_cases
    ):
        raise AppException(
            "DEMO_USER_PROFILE_CONFLICT",
            f"Demo account has an unexpected role or profile: {request.email}",
            409,
        )


def _align_existing_staff_password(
    session: Session,
    user: User,
    password: str,
    *,
    update: bool,
) -> None:
    password_matches = bool(
        user.password_hash and verify_password(password, user.password_hash)
    )
    hash_needs_upgrade = bool(
        password_matches
        and user.password_hash
        and password_needs_rehash(user.password_hash)
    )
    if password_matches and not hash_needs_upgrade:
        session.rollback()
        return
    if not update:
        session.rollback()
        raise AppException(
            "DEMO_USER_PASSWORD_MISMATCH",
            f"Demo account password does not match configured environment: {user.email}",
            409,
        )
    user.password_hash = hash_password(password)
    session.commit()


def seed(session: Session, *, create_missing: bool = True) -> dict[str, dict[str, str]]:
    passwords = _required_environment()
    users = UserRepository(session)
    staff_service = StaffService(session)
    result: dict[str, dict[str, str]] = {}

    for first_name, last_name, email, role, specializations, regions, password_env in DEMO_STAFF:
        request = StaffCreate(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=passwords[password_env],
            role=role,
            specializations=specializations,
            regions=regions,
            max_active_cases=10,
        )
        existing = users.get_by_email(email)
        if existing is None:
            if not create_missing:
                raise AppException("DEMO_USER_MISSING", f"Demo account is missing: {email}", 404)
            created = staff_service.create_staff(request)
            user_id = created.id
        else:
            _validate_existing_staff(existing, request)
            user_id = existing.id
            _align_existing_staff_password(
                session,
                existing,
                passwords[password_env],
                update=create_missing,
            )
        result[email] = {"id": str(user_id), "role": role.value}

    gsm = normalize_turkish_gsm(os.getenv("DEMO_CUSTOMER_GSM", "05550000001"))
    customer = users.get_by_gsm(gsm)
    if customer is None:
        if not create_missing:
            raise AppException("DEMO_USER_MISSING", "Demo customer is missing", 404)
        OtpService(session).request_challenge(gsm)
        customer = CustomerService(session).register(
            CustomerRegisterRequest(
                first_name="Demo",
                last_name="Müşteri",
                gsm=gsm,
                email=None,
                otp_code=os.getenv("DEMO_OTP_CODE", "1234"),
            )
        )
    elif (
        customer.role is not UserRole.CUSTOMER
        or not customer.is_active
        or customer.first_name != "Demo"
        or customer.last_name != "Müşteri"
    ):
        raise AppException("DEMO_USER_PROFILE_CONFLICT", "Demo customer has unexpected identity data", 409)
    result["customer"] = {"id": str(customer.id), "role": UserRole.CUSTOMER.value, "gsm": gsm}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate without creating missing users")
    args = parser.parse_args()
    try:
        with Session(_get_engine()) as session:
            result = seed(session, create_missing=not args.check)
    except (ValueError, AppException, ValidationError) as exc:
        code = getattr(exc, "code", type(exc).__name__)
        print(f"Demo user seed failed: {code}: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print("Demo user seed failed due to a database error", file=sys.stderr)
        return 1

    for account, value in result.items():
        label = value.get("gsm", account)
        print(f"{label} {value['role']} {value['id']}")
    print("DEMO_USERS_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

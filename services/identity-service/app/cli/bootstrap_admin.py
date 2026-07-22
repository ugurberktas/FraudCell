"""Create the first Identity Service Admin account from environment variables."""
from __future__ import annotations

import os
import sys

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.db.session import _get_engine
from app.schemas.staff import StaffCreate, StaffRole
from app.security.passwords import PasswordPolicyError, validate_password_policy
from app.services.staff_service import StaffService


_ENVIRONMENT_FIELDS = {
    "BOOTSTRAP_ADMIN_FIRST_NAME": "first_name",
    "BOOTSTRAP_ADMIN_LAST_NAME": "last_name",
    "BOOTSTRAP_ADMIN_EMAIL": "email",
    "BOOTSTRAP_ADMIN_PASSWORD": "password",
}


def _format_validation_errors(exc: ValidationError) -> str:
    """Format Pydantic errors without ever rendering submitted values."""
    formatted: list[str] = []
    for error in exc.errors(
        include_url=False,
        include_context=True,
        include_input=False,
    ):
        location = ".".join(str(part) for part in error.get("loc", ()))
        field = location or "configuration"

        if field == "password":
            policy_error = error.get("ctx", {}).get("error")
            if isinstance(policy_error, PasswordPolicyError):
                reason = ", ".join(policy_error.violations)
            else:
                reason = "password is invalid"
        else:
            reason = error.get("msg", "invalid value")

        formatted.append(f"{field}: {reason}")
    return "; ".join(formatted)


def main() -> int:
    values = {name: os.environ.get(name) for name in _ENVIRONMENT_FIELDS}
    missing = [name for name, value in values.items() if value is None or not value.strip()]
    if missing:
        print(
            f"Missing required environment variables: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    try:
        validate_password_policy(values["BOOTSTRAP_ADMIN_PASSWORD"])
    except PasswordPolicyError as exc:
        print(
            f"Password policy failed: {', '.join(exc.violations)}",
            file=sys.stderr,
        )
        return 1

    try:
        request = StaffCreate(
            first_name=values["BOOTSTRAP_ADMIN_FIRST_NAME"],
            last_name=values["BOOTSTRAP_ADMIN_LAST_NAME"],
            email=values["BOOTSTRAP_ADMIN_EMAIL"],
            password=values["BOOTSTRAP_ADMIN_PASSWORD"],
            role=StaffRole.ADMIN,
            specializations=[],
            regions=[],
            max_active_cases=10,
        )
    except ValidationError as exc:
        details = _format_validation_errors(exc)
        print(f"Invalid bootstrap Admin configuration: {details}", file=sys.stderr)
        return 1

    try:
        with Session(_get_engine()) as session:
            result = StaffService(session).bootstrap_admin(request)
    except AppException as exc:
        print(f"Admin bootstrap failed: {exc.code}", file=sys.stderr)
        return 1
    except Exception:
        print("Admin bootstrap failed due to a database error", file=sys.stderr)
        return 1

    state = "created" if result.created else "already existed"
    print(f"Admin {result.email}: {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

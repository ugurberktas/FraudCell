"""Argon2id password hashing and password-policy enforcement."""
from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


PASSWORD_TOO_SHORT = "PASSWORD_TOO_SHORT"
PASSWORD_UPPERCASE_REQUIRED = "PASSWORD_UPPERCASE_REQUIRED"
PASSWORD_DIGIT_REQUIRED = "PASSWORD_DIGIT_REQUIRED"
PASSWORD_SPECIAL_REQUIRED = "PASSWORD_SPECIAL_REQUIRED"

_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


class PasswordPolicyError(ValueError):
    """Raised with every unmet password-policy rule."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = tuple(violations)
        super().__init__(", ".join(violations))


def validate_password_policy(password: str) -> None:
    """Validate a plaintext password and report all unmet policy rules."""
    violations: list[str] = []
    if not password or not password.strip() or len(password) < 8:
        violations.append(PASSWORD_TOO_SHORT)
    if not any(character.isupper() for character in password):
        violations.append(PASSWORD_UPPERCASE_REQUIRED)
    if not any(character.isdigit() for character in password):
        violations.append(PASSWORD_DIGIT_REQUIRED)
    if not any(
        not character.isalnum() and not character.isspace() for character in password
    ):
        violations.append(PASSWORD_SPECIAL_REQUIRED)
    if violations:
        raise PasswordPolicyError(violations)


def hash_password(password: str) -> str:
    """Validate and hash a password with Argon2id."""
    validate_password_policy(password)
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether a plaintext password matches an Argon2 hash."""
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """Return whether a stored hash should be upgraded to current parameters."""
    try:
        return _PASSWORD_HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True

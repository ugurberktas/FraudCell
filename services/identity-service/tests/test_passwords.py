"""Tests for Argon2id hashing and the staff password policy."""
import pytest
from argon2 import PasswordHasher, Type

from app.security.passwords import (
    PASSWORD_DIGIT_REQUIRED,
    PASSWORD_SPECIAL_REQUIRED,
    PASSWORD_TOO_SHORT,
    PASSWORD_UPPERCASE_REQUIRED,
    PasswordPolicyError,
    hash_password,
    password_needs_rehash,
    validate_password_policy,
    verify_password,
)


def policy_violations(password: str) -> tuple[str, ...]:
    with pytest.raises(PasswordPolicyError) as exc_info:
        validate_password_policy(password)
    return exc_info.value.violations


def test_valid_password_is_accepted() -> None:
    assert validate_password_policy("Strong1!") is None


def test_short_password_is_rejected() -> None:
    assert PASSWORD_TOO_SHORT in policy_violations("Ab1!")


def test_uppercase_is_required() -> None:
    assert PASSWORD_UPPERCASE_REQUIRED in policy_violations("lowercase1!")


def test_digit_is_required() -> None:
    assert PASSWORD_DIGIT_REQUIRED in policy_violations("NoDigits!")


def test_special_character_is_required() -> None:
    assert PASSWORD_SPECIAL_REQUIRED in policy_violations("NoSpecial1")


def test_whitespace_does_not_count_as_a_special_character() -> None:
    assert PASSWORD_SPECIAL_REQUIRED in policy_violations("NoSpecial1 ")


def test_blank_password_is_rejected() -> None:
    violations = policy_violations("   ")
    assert PASSWORD_TOO_SHORT in violations


def test_multiple_policy_violations_are_reported_together() -> None:
    violations = set(policy_violations("short"))
    assert violations == {
        PASSWORD_TOO_SHORT,
        PASSWORD_UPPERCASE_REQUIRED,
        PASSWORD_DIGIT_REQUIRED,
        PASSWORD_SPECIAL_REQUIRED,
    }


def test_argon2id_hash_and_password_verification() -> None:
    password = "Strong1!Password"
    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password, password_hash) is True
    assert verify_password("Wrong1!Password", password_hash) is False
    assert verify_password(password, "not-a-valid-hash") is False


def test_password_needs_rehash() -> None:
    current_hash = hash_password("Strong1!Password")
    old_parameters_hash = PasswordHasher(
        time_cost=1,
        memory_cost=8192,
        parallelism=1,
        hash_len=16,
        salt_len=8,
        type=Type.ID,
    ).hash("Strong1!Password")

    assert password_needs_rehash(current_hash) is False
    assert password_needs_rehash(old_parameters_hash) is True
    assert password_needs_rehash("not-a-valid-hash") is True

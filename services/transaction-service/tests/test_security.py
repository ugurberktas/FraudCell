import uuid

import pytest

from app.common.exceptions import AppException
from app.core.config import settings
from app.security.tokens import decode_access_token
from tests.conftest import TEST_JWT_SECRET, access_token


def test_identity_access_token_is_verified(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", TEST_JWT_SECRET)
    user_id = uuid.uuid4()
    claims = decode_access_token(access_token(user_id, "CUSTOMER"))
    assert claims["user_id"] == str(user_id)
    assert claims["type"] == "access"


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "refresh"},
        {"iss": "wrong-issuer"},
        {"aud": "wrong-audience"},
    ],
)
def test_non_access_or_wrong_identity_claims_are_rejected(monkeypatch, overrides):
    monkeypatch.setattr(settings, "jwt_secret", TEST_JWT_SECRET)
    token = access_token(uuid.uuid4(), "CUSTOMER", **overrides)
    with pytest.raises(AppException) as caught:
        decode_access_token(token)
    assert caught.value.status_code == 401

"""JWT access tokens and opaque refresh-token primitives."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import uuid

import jwt

from app.common.exceptions import AppException
from app.core.config import jwt_secret_is_unsafe, settings
from app.models.user import User


ALLOWED_JWT_ALGORITHMS = {"HS256"}


def _jwt_configuration() -> tuple[str, str]:
    if settings.jwt_algorithm not in ALLOWED_JWT_ALGORITHMS:
        raise RuntimeError("JWT algorithm is not allowed")
    if jwt_secret_is_unsafe(settings.jwt_secret):
        raise RuntimeError("JWT_SECRET must contain at least 32 characters")
    return settings.jwt_secret, settings.jwt_algorithm


def create_access_token(user: User, now: datetime | None = None) -> str:
    secret, algorithm = _jwt_configuration()
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=settings.access_token_expire_minutes)
    profile = user.staff_profile
    specializations = list(profile.specializations) if profile is not None else []
    regions = list(profile.regions) if profile is not None else []
    user_id = str(user.id)
    claims = {
        "sub": user_id,
        "user_id": user_id,
        "role": user.role.value,
        "specializations": specializations,
        "regions": regions,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(claims, secret, algorithm=algorithm)


def decode_access_token(token: str) -> dict:
    secret, algorithm = _jwt_configuration()
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={
                "require": [
                    "sub",
                    "user_id",
                    "role",
                    "specializations",
                    "regions",
                    "type",
                    "jti",
                    "iat",
                    "exp",
                    "iss",
                    "aud",
                ]
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppException(
            "TOKEN_EXPIRED", "Access token has expired", status_code=401
        ) from exc
    except jwt.PyJWTError as exc:
        raise AppException("TOKEN_INVALID", "Access token is invalid", status_code=401) from exc

    if claims.get("type") != "access" or claims.get("sub") != claims.get("user_id"):
        raise AppException("TOKEN_INVALID", "Access token is invalid", status_code=401)
    return claims


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

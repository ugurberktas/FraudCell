"""Identity-issued access JWT verification."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import uuid

import jwt

from app.common.exceptions import AppException
from app.core.config import settings


ALLOWED_JWT_ALGORITHMS = {"HS256"}


class UserRole(str, Enum):
    CUSTOMER = "CUSTOMER"
    ANALYST = "ANALYST"
    SUPERVISOR = "SUPERVISOR"
    ADMIN = "ADMIN"


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: uuid.UUID
    role: UserRole


def _jwt_configuration() -> tuple[str, str]:
    if settings.jwt_algorithm not in ALLOWED_JWT_ALGORITHMS:
        raise RuntimeError("JWT algorithm is not allowed")
    if len(settings.jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET must contain at least 32 characters")
    return settings.jwt_secret, settings.jwt_algorithm


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
        raise AppException("TOKEN_EXPIRED", "Access token has expired", 401) from exc
    except jwt.PyJWTError as exc:
        raise AppException("TOKEN_INVALID", "Access token is invalid", 401) from exc

    if claims.get("type") != "access" or claims.get("sub") != claims.get("user_id"):
        raise AppException("TOKEN_INVALID", "Access token is invalid", 401)
    try:
        uuid.UUID(str(claims["user_id"]))
        UserRole(claims["role"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppException("TOKEN_INVALID", "Access token is invalid", 401) from exc
    return claims

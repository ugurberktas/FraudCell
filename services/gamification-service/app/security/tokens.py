from dataclasses import dataclass
from enum import Enum
import uuid

import jwt

from app.common.exceptions import AppException
from app.core.config import settings


class UserRole(str, Enum):
    CUSTOMER = "CUSTOMER"
    ANALYST = "ANALYST"
    SUPERVISOR = "SUPERVISOR"
    ADMIN = "ADMIN"


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: uuid.UUID
    role: UserRole


def decode_access_token(token: str) -> dict:
    if settings.jwt_algorithm != "HS256" or len(settings.jwt_secret) < 32:
        raise RuntimeError("Secure JWT configuration is required")
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "user_id", "role", "type", "jti", "iat", "exp", "iss", "aud"]},
        )
        if claims.get("type") != "access" or claims.get("sub") != claims.get("user_id"):
            raise ValueError
        uuid.UUID(str(claims["user_id"]))
        UserRole(claims["role"])
        return claims
    except jwt.ExpiredSignatureError as exc:
        raise AppException("TOKEN_EXPIRED", "Access token has expired", 401) from exc
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise AppException("TOKEN_INVALID", "Access token is invalid", 401) from exc

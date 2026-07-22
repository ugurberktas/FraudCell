"""JWT authentication and role dependencies."""
from collections.abc import Callable
import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.common.exceptions import AppException
from app.security.tokens import AuthenticatedUser, UserRole, decode_access_token


_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppException("TOKEN_INVALID", "Access token is required", 401)
    claims = decode_access_token(credentials.credentials)
    return AuthenticatedUser(
        user_id=uuid.UUID(claims["user_id"]), role=UserRole(claims["role"])
    )


def require_roles(*roles: UserRole) -> Callable:
    allowed = frozenset(roles)

    def dependency(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if user.role not in allowed:
            raise AppException("FORBIDDEN", "Access is forbidden", 403)
        return user

    return dependency

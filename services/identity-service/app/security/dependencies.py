"""JWT authentication and authorization dependencies."""
import uuid

from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.db.dependencies import get_db
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.security.tokens import decode_access_token
from app.security.client_ip import get_client_ip
from app.services.audit_service import AuditAction, AuditResult, AuditService


_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppException("TOKEN_INVALID", "Access token is required", status_code=401)

    claims = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(claims["user_id"])
    except (ValueError, TypeError) as exc:
        raise AppException("TOKEN_INVALID", "Access token is invalid", status_code=401) from exc

    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise AppException("TOKEN_INVALID", "Access token is invalid", status_code=401)
    if not user.is_active:
        AuditService(db).record_and_commit(
            actor_user_id=user.id,
            action=AuditAction.ACCESS_DENIED,
            result=AuditResult.FAILURE,
            ip_address=get_client_ip(request),
            resource_type="ROUTE",
            resource_id=request.url.path,
            details={"method": request.method, "reason": "INACTIVE_USER"},
        )
        raise AppException("FORBIDDEN", "Access is forbidden", status_code=403)
    return user


def require_roles(*roles: UserRole) -> Callable:
    allowed_roles = frozenset(roles)

    def dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if current_user.role not in allowed_roles:
            AuditService(db).record_and_commit(
                actor_user_id=current_user.id,
                action=AuditAction.ACCESS_DENIED,
                result=AuditResult.FAILURE,
                ip_address=get_client_ip(request),
                resource_type="ROUTE",
                resource_id=request.url.path,
                details={
                    "method": request.method,
                    "required_roles": sorted(role.value for role in allowed_roles),
                    "actual_role": current_user.role.value,
                },
            )
            raise AppException("FORBIDDEN", "Access is forbidden", status_code=403)
        return current_user

    return dependency


require_admin = require_roles(UserRole.ADMIN)

"""Immutable security audit recording with recursive sanitization."""
from __future__ import annotations

from enum import Enum
import logging
import uuid

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.repositories.audit_repository import AuditRepository


logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    AUTH_LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
    AUTH_LOGIN_FAILED = "AUTH_LOGIN_FAILED"
    AUTH_ACCOUNT_LOCKED = "AUTH_ACCOUNT_LOCKED"
    AUTH_TOKEN_REFRESHED = "AUTH_TOKEN_REFRESHED"
    AUTH_TOKEN_REUSE_DETECTED = "AUTH_TOKEN_REUSE_DETECTED"
    AUTH_LOGOUT = "AUTH_LOGOUT"
    STAFF_ACCOUNT_CREATED = "STAFF_ACCOUNT_CREATED"
    ACCESS_DENIED = "ACCESS_DENIED"
    ROLE_CHANGED = "ROLE_CHANGED"


class AuditResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


_SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "otp",
    "otp_code",
    "access_token",
    "refresh_token",
    "token",
    "authorization",
    "secret",
    "jwt_secret",
}


def sanitize_audit_details(value):
    if isinstance(value, dict):
        sanitized = {}
        for key, nested_value in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            if normalized_key in _SENSITIVE_KEYS:
                continue
            sanitized[str(key)] = sanitize_audit_details(nested_value)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [sanitize_audit_details(item) for item in value]
    return value


class AuditService:
    def __init__(
        self, session: Session, repository: AuditRepository | None = None
    ) -> None:
        self.session = session
        self.repository = repository or AuditRepository(session)

    def record(
        self,
        *,
        action: AuditAction,
        result: AuditResult,
        actor_user_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict | list | None = None,
    ) -> AuditLog | None:
        try:
            with self.session.begin_nested():
                return self.repository.create(
                    actor_user_id=actor_user_id,
                    action=action.value,
                    ip_address=ip_address[:45] if ip_address else None,
                    result=result.value,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    details=sanitize_audit_details(details),
                )
        except Exception:  # noqa: BLE001 - audit failure must not bypass security
            logger.error("Audit record could not be written for action %s", action.value)
            return None

    def record_and_commit(self, **kwargs) -> AuditLog | None:
        record = self.record(**kwargs)
        try:
            self.session.commit()
        except Exception:  # noqa: BLE001
            self.session.rollback()
            logger.error("Audit transaction could not be committed")
        return record

    def audit_role_change(
        self,
        *,
        actor_user_id: uuid.UUID,
        target_user_id: uuid.UUID,
        old_role: str,
        new_role: str,
        ip_address: str | None = None,
    ) -> AuditLog | None:
        return self.record(
            actor_user_id=actor_user_id,
            action=AuditAction.ROLE_CHANGED,
            result=AuditResult.SUCCESS,
            ip_address=ip_address,
            resource_type="USER",
            resource_id=str(target_user_id),
            details={"old_role": old_role, "new_role": new_role},
        )

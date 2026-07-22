"""Refresh session issuance, rotation, reuse detection, and logout."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.core.config import settings
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.security.tokens import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.services.audit_service import AuditAction, AuditResult, AuditService


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class TokenService:
    def __init__(
        self,
        session: Session,
        repository: RefreshTokenRepository | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or RefreshTokenRepository(session)
        self.audit = AuditService(session)

    def issue_for_user(self, user: User, now: datetime | None = None) -> IssuedTokens:
        issued, _record = self._issue_with_record(user, now)
        return issued

    def _issue_with_record(
        self, user: User, now: datetime | None = None
    ) -> tuple[IssuedTokens, RefreshToken]:
        issued_at = now or datetime.now(timezone.utc)
        raw_refresh = generate_refresh_token()
        record = self.repository.create(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=issued_at + timedelta(days=settings.refresh_token_expire_days),
        )
        return (
            IssuedTokens(
                access_token=create_access_token(user, issued_at),
                refresh_token=raw_refresh,
            ),
            record,
        )

    def rotate(
        self, raw_refresh: str, ip_address: str | None = None
    ) -> tuple[IssuedTokens, User]:
        now = datetime.now(timezone.utc)
        token = self.repository.get_by_hash_for_update(hash_refresh_token(raw_refresh))
        if token is None:
            self.session.rollback()
            raise AppException(
                "INVALID_REFRESH_TOKEN", "Refresh token is invalid", status_code=401
            )

        if token.revoked_at is not None:
            if token.replaced_by_token_id is not None:
                self.repository.revoke_all_active(token.user_id, now)
                self.audit.record(
                    actor_user_id=token.user_id,
                    action=AuditAction.AUTH_TOKEN_REUSE_DETECTED,
                    result=AuditResult.FAILURE,
                    ip_address=ip_address,
                    resource_type="REFRESH_TOKEN",
                    resource_id=str(token.id),
                    details={"all_active_sessions_revoked": True},
                )
                self.session.commit()
                raise AppException(
                    "TOKEN_REUSE_DETECTED",
                    "Refresh token reuse was detected",
                    status_code=401,
                )
            self.session.rollback()
            raise AppException(
                "INVALID_REFRESH_TOKEN", "Refresh token is invalid", status_code=401
            )

        if _utc(token.expires_at) <= now or not token.user.is_active:
            self.session.rollback()
            raise AppException(
                "INVALID_REFRESH_TOKEN", "Refresh token is invalid", status_code=401
            )

        try:
            user = token.user
            issued, replacement = self._issue_with_record(user, now)
            token.revoked_at = now
            token.replaced_by_token_id = replacement.id
            self.audit.record(
                actor_user_id=user.id,
                action=AuditAction.AUTH_TOKEN_REFRESHED,
                result=AuditResult.SUCCESS,
                ip_address=ip_address,
                resource_type="REFRESH_TOKEN",
                resource_id=str(replacement.id),
                details={"replaced_record_id": str(token.id)},
            )
            self.session.commit()
            return issued, user
        except Exception:
            self.session.rollback()
            raise

    def logout(self, raw_refresh: str, ip_address: str | None = None) -> None:
        token = self.repository.get_by_hash_for_update(hash_refresh_token(raw_refresh))
        if token is None or token.revoked_at is not None:
            self.session.rollback()
            return
        token.revoked_at = datetime.now(timezone.utc)
        self.audit.record(
            actor_user_id=token.user_id,
            action=AuditAction.AUTH_LOGOUT,
            result=AuditResult.SUCCESS,
            ip_address=ip_address,
            resource_type="REFRESH_TOKEN",
            resource_id=str(token.id),
            details={"session_revoked": True},
        )
        self.session.commit()

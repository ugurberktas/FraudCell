"""Customer and staff authentication orchestration."""
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import math
import secrets

from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.core.config import settings
from app.models.otp_challenge import OtpPurpose
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.auth import AuthUserResponse, TokenResponse
from app.security.passwords import hash_password, verify_password
from app.services.otp_service import OtpService
from app.services.token_service import IssuedTokens, TokenService
from app.services.audit_service import AuditAction, AuditResult, AuditService


LOCK_THRESHOLD = 5
LOCK_DURATION = timedelta(minutes=15)
_DUMMY_PASSWORD_HASH = hash_password(f"D{secrets.token_urlsafe(24)}1!")


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _authentication_failed() -> AppException:
    return AppException(
        "AUTHENTICATION_FAILED", "Authentication failed", status_code=401
    )


class AuthService:
    def __init__(
        self,
        session: Session,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.users = UserRepository(session)
        self.otp = OtpService(session)
        self.tokens = TokenService(session)
        self.audit = AuditService(session)

    def request_customer_login_otp(self, gsm: str) -> None:
        user = self.users.get_active_customer_by_gsm(gsm)
        if user is not None:
            self.otp.request_challenge(gsm, OtpPurpose.LOGIN)
        else:
            self.session.rollback()

    def customer_login(
        self, gsm: str, otp_code: str, ip_address: str | None = None
    ) -> TokenResponse:
        user = self.users.get_active_customer_by_gsm(gsm)
        if user is None:
            self.audit.record(
                action=AuditAction.AUTH_LOGIN_FAILED,
                result=AuditResult.FAILURE,
                ip_address=ip_address,
                details={"authentication_method": "CUSTOMER_OTP", "reason": "AUTHENTICATION_FAILED"},
            )
            self.session.commit()
            raise _authentication_failed()

        try:
            now = self.clock()
            challenge = self.otp.verify(
                gsm,
                otp_code,
                now,
                OtpPurpose.LOGIN,
                commit_failure=False,
            )
            issued = self.tokens.issue_for_user(user, now)
            challenge.consumed_at = now
            self.audit.record(
                actor_user_id=user.id,
                action=AuditAction.AUTH_LOGIN_SUCCESS,
                result=AuditResult.SUCCESS,
                ip_address=ip_address,
                resource_type="USER",
                resource_id=str(user.id),
                details={"authentication_method": "CUSTOMER_OTP"},
            )
            self.session.commit()
            return self._token_response(user, issued)
        except AppException as exc:
            self.audit.record(
                actor_user_id=user.id,
                action=AuditAction.AUTH_LOGIN_FAILED,
                result=AuditResult.FAILURE,
                ip_address=ip_address,
                resource_type="USER",
                resource_id=str(user.id),
                details={
                    "authentication_method": "CUSTOMER_OTP",
                    "reason": exc.code,
                },
            )
            self.session.commit()
            raise
        except Exception:
            self.session.rollback()
            raise

    def staff_login(
        self, email: str, password: str, ip_address: str | None = None
    ) -> TokenResponse:
        user = self.users.get_by_email_for_update(email)
        allowed_roles = {UserRole.ANALYST, UserRole.SUPERVISOR, UserRole.ADMIN}
        if (
            user is None
            or user.role not in allowed_roles
            or not user.is_active
            or user.password_hash is None
        ):
            # Equalize the expensive Argon2 verification path without exposing
            # whether the normalized email belongs to a login-eligible account.
            verify_password(password, _DUMMY_PASSWORD_HASH)
            self.audit.record(
                actor_user_id=user.id if user is not None else None,
                action=AuditAction.AUTH_LOGIN_FAILED,
                result=AuditResult.FAILURE,
                ip_address=ip_address,
                resource_type="USER" if user is not None else None,
                resource_id=str(user.id) if user is not None else None,
                details={"authentication_method": "PASSWORD", "reason": "AUTHENTICATION_FAILED"},
            )
            self.session.commit()
            raise _authentication_failed()

        now = self.clock()
        if user.locked_until is not None:
            locked_until = _utc(user.locked_until)
            if locked_until > now:
                locked_exception = self._account_locked(locked_until, now)
                self.audit.record(
                    actor_user_id=user.id,
                    action=AuditAction.AUTH_ACCOUNT_LOCKED,
                    result=AuditResult.FAILURE,
                    ip_address=ip_address,
                    resource_type="USER",
                    resource_id=str(user.id),
                    details={
                        "remaining_seconds": locked_exception.details[
                            "remaining_seconds"
                        ]
                    },
                )
                self.session.commit()
                raise locked_exception
            user.failed_login_count = 0
            user.locked_until = None

        if not verify_password(password, user.password_hash):
            user.failed_login_count += 1
            self.audit.record(
                actor_user_id=user.id,
                action=AuditAction.AUTH_LOGIN_FAILED,
                result=AuditResult.FAILURE,
                ip_address=ip_address,
                resource_type="USER",
                resource_id=str(user.id),
                details={"authentication_method": "PASSWORD", "attempt": user.failed_login_count},
            )
            if user.failed_login_count >= LOCK_THRESHOLD:
                user.failed_login_count = LOCK_THRESHOLD
                user.locked_until = now + LOCK_DURATION
                self.audit.record(
                    actor_user_id=user.id,
                    action=AuditAction.AUTH_ACCOUNT_LOCKED,
                    result=AuditResult.FAILURE,
                    ip_address=ip_address,
                    resource_type="USER",
                    resource_id=str(user.id),
                    details={"lock_duration_seconds": int(LOCK_DURATION.total_seconds())},
                )
                locked_until = user.locked_until
                self.session.commit()
                raise self._account_locked(locked_until, now)
            self.session.commit()
            raise _authentication_failed()

        try:
            user.failed_login_count = 0
            user.locked_until = None
            issued = self.tokens.issue_for_user(user, now)
            self.audit.record(
                actor_user_id=user.id,
                action=AuditAction.AUTH_LOGIN_SUCCESS,
                result=AuditResult.SUCCESS,
                ip_address=ip_address,
                resource_type="USER",
                resource_id=str(user.id),
                details={"authentication_method": "PASSWORD"},
            )
            self.session.commit()
            return self._token_response(user, issued)
        except Exception:
            self.session.rollback()
            raise

    @staticmethod
    def _account_locked(locked_until: datetime, now: datetime) -> AppException:
        remaining_seconds = max(
            1, math.ceil((_utc(locked_until) - now).total_seconds())
        )
        return AppException(
            "ACCOUNT_LOCKED",
            "Account is temporarily locked",
            status_code=429,
            details={"remaining_seconds": remaining_seconds},
            headers={"Retry-After": str(remaining_seconds)},
        )

    @staticmethod
    def _token_response(user: User, issued: IssuedTokens) -> TokenResponse:
        return TokenResponse(
            access_token=issued.access_token,
            refresh_token=issued.refresh_token,
            expires_in=settings.access_token_expire_minutes * 60,
            user=AuthUserResponse(
                id=user.id,
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                gsm=user.gsm,
                role=user.role.value,
            ),
        )

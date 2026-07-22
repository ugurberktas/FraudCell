"""OTP challenge creation and verification."""
from datetime import datetime, timedelta, timezone
import hmac

from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.core.config import settings
from app.models.otp_challenge import OtpChallenge
from app.repositories.otp_repository import OtpRepository


OTP_TTL = timedelta(minutes=5)
MAX_FAILED_ATTEMPTS = 5


class OtpService:
    def __init__(self, session: Session, repository: OtpRepository | None = None) -> None:
        self.session = session
        self.repository = repository or OtpRepository(session)

    def request_challenge(self, gsm: str) -> OtpChallenge:
        now = datetime.now(timezone.utc)
        try:
            self.repository.invalidate_unconsumed(gsm, now)
            challenge = self.repository.create(gsm=gsm, expires_at=now + OTP_TTL)
            self.session.commit()
            self.session.refresh(challenge)
            return challenge
        except Exception:
            self.session.rollback()
            raise

    def verify(self, gsm: str, supplied_code: str, now: datetime) -> OtpChallenge:
        challenge = self.repository.get_latest_for_update(gsm)
        if challenge is None or challenge.consumed_at is not None:
            raise AppException("OTP_INVALID", "OTP code is invalid", status_code=400)
        expires_at = challenge.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise AppException("OTP_EXPIRED", "OTP code has expired", status_code=400)
        if challenge.failed_attempts >= MAX_FAILED_ATTEMPTS:
            raise AppException("OTP_INVALID", "OTP code is invalid", status_code=400)

        if not hmac.compare_digest(supplied_code, settings.demo_otp_code):
            challenge.failed_attempts += 1
            if challenge.failed_attempts >= MAX_FAILED_ATTEMPTS:
                challenge.consumed_at = now
            self.session.commit()
            raise AppException("OTP_INVALID", "OTP code is invalid", status_code=400)
        return challenge

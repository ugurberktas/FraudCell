"""OTP challenge persistence operations."""
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.otp_challenge import OtpChallenge, OtpPurpose


class OtpRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def invalidate_unconsumed(
        self, gsm: str, purpose: OtpPurpose, consumed_at: datetime
    ) -> None:
        self.session.execute(
            update(OtpChallenge)
            .where(
                OtpChallenge.gsm == gsm,
                OtpChallenge.purpose == purpose,
                OtpChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=consumed_at)
        )

    def create(
        self, *, gsm: str, purpose: OtpPurpose, expires_at: datetime
    ) -> OtpChallenge:
        challenge = OtpChallenge(gsm=gsm, purpose=purpose, expires_at=expires_at)
        self.session.add(challenge)
        self.session.flush()
        return challenge

    def get_latest_for_update(
        self, gsm: str, purpose: OtpPurpose
    ) -> OtpChallenge | None:
        statement = (
            select(OtpChallenge)
            .where(OtpChallenge.gsm == gsm, OtpChallenge.purpose == purpose)
            .order_by(OtpChallenge.created_at.desc(), OtpChallenge.id.desc())
            .limit(1)
            .with_for_update()
        )
        return self.session.scalar(statement)

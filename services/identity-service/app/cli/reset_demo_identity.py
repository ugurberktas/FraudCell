"""Reset only transient authentication state for fixed demo users."""
from __future__ import annotations

import sys

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import _get_engine
from app.models.otp_challenge import OtpChallenge
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.customer import normalize_turkish_gsm
from app.cli.seed_demo_users import DEMO_STAFF


def reset(session: Session) -> int:
    emails = [item[2] for item in DEMO_STAFF]
    gsm = normalize_turkish_gsm(__import__("os").getenv("DEMO_CUSTOMER_GSM", "05550000001"))
    users = list(session.scalars(select(User).where((User.email.in_(emails)) | (User.gsm == gsm))))
    ids = [user.id for user in users]
    if ids:
        session.execute(delete(RefreshToken).where(RefreshToken.user_id.in_(ids)))
    session.execute(delete(OtpChallenge).where(OtpChallenge.gsm == gsm))
    for user in users:
        user.failed_login_count = 0
        user.locked_until = None
    session.commit()
    return len(users)


def main() -> int:
    try:
        with Session(_get_engine()) as session:
            count = reset(session)
        print(f"Demo identity state reset: {count} users")
        return 0
    except Exception:
        print("Demo identity reset failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

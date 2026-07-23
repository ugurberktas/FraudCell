"""Create zero-point profiles for real demo analyst UUIDs."""
from __future__ import annotations

import os
import argparse
import sys
import uuid

from sqlalchemy.orm import Session

from app.db.session import _get_engine
from app.models import AnalystProfile
from app.repositories.gamification_repository import GamificationRepository

ID_ENVIRONMENTS = ("DEMO_CARD_ANALYST_ID", "DEMO_ACCOUNT_ANALYST_ID", "DEMO_AML_ANALYST_ID")


def analyst_ids() -> list[uuid.UUID]:
    result = []
    for name in ID_ENVIRONMENTS:
        raw = os.getenv(name, "")
        if not raw:
            raise ValueError(f"Missing analyst UUID: {name}")
        try:
            result.append(uuid.UUID(raw))
        except ValueError as exc:
            raise ValueError(f"Invalid analyst UUID: {name}") from exc
    return result


def seed(session: Session, *, create_missing: bool = True) -> list[AnalystProfile]:
    repository = GamificationRepository(session)
    profiles = []
    for analyst_id in analyst_ids():
        profile = repository.get_profile(analyst_id)
        if profile is None:
            if not create_missing:
                raise ValueError(f"Gamification demo profile is missing: {analyst_id}")
            profile = AnalystProfile(
                analyst_id=analyst_id,
                total_points=0,
                resolved_cases=0,
                level="BRONZ",
            )
            session.add(profile)
        profiles.append(profile)
    session.commit()
    return profiles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        with Session(_get_engine()) as session:
            profiles = seed(session, create_missing=not args.check)
            profile_ids = [str(profile.analyst_id) for profile in profiles]
        for analyst_id in profile_ids:
            print(f"Gamification profile ready: {analyst_id}")
        return 0
    except Exception as exc:
        print(f"Gamification demo profile seed failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

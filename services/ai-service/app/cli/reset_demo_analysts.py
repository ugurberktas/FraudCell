"""Reset only demo analyst capacity counters."""
from __future__ import annotations

import sys

from sqlalchemy.orm import Session

from app.cli.seed_demo_analysts import _resolved
from app.db.session import _get_engine
from app.repositories.analyst_repository import AnalystRepository


def reset(session: Session) -> int:
    repository = AnalystRepository(session)
    count = 0
    for analyst_id, _specializations, _regions, _accuracy in _resolved():
        profile = repository.get(analyst_id)
        if profile is not None:
            profile.active_cases = 0
            count += 1
    session.commit()
    return count


def main() -> int:
    try:
        with Session(_get_engine()) as session:
            count = reset(session)
        print(f"AI demo analyst capacity reset: {count}")
        return 0
    except Exception as exc:
        print(f"AI demo reset failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

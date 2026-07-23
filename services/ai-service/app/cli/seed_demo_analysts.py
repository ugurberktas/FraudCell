"""Idempotently sync demo analyst profiles using Identity-issued UUIDs."""
from __future__ import annotations

import os
import argparse
import sys
import uuid

from sqlalchemy.orm import Session

from app.db.session import _get_engine
from app.schemas.scoring import AnalystSyncRequest
from app.services.analyst_service import AnalystService
from app.repositories.analyst_repository import AnalystRepository
from app.schemas.scoring import AnalystProfileRead


PROFILES = (
    ("DEMO_CARD_ANALYST_ID", ["CALINTI_KART"], ["TR", "EU"], "0.9200"),
    ("DEMO_ACCOUNT_ANALYST_ID", ["HESAP_ELE_GECIRME"], ["TR", "EU"], "0.9000"),
    ("DEMO_AML_ANALYST_ID", ["PARA_AKLAMA"], ["TR", "EU", "GLOBAL"], "0.9400"),
)


def _resolved() -> list[tuple[uuid.UUID, list[str], list[str], str]]:
    result = []
    for name, specializations, regions, accuracy in PROFILES:
        raw = os.getenv(name, "")
        if not raw:
            raise ValueError(f"Missing analyst UUID: {name}")
        try:
            analyst_id = uuid.UUID(raw)
        except ValueError as exc:
            raise ValueError(f"Invalid analyst UUID: {name}") from exc
        result.append((analyst_id, specializations, regions, accuracy))
    return result


def seed(session: Session, *, create_missing: bool = True) -> list[dict]:
    service = AnalystService(session)
    repository = AnalystRepository(session)
    rows = []
    for analyst_id, specializations, regions, accuracy in _resolved():
        request = AnalystSyncRequest(
                analyst_id=analyst_id,
                specializations=specializations,
                regions=regions,
                active_cases=0,
                max_active_cases=10,
                accuracy_rate=accuracy,
                is_active=True,
            )
        existing = repository.get(analyst_id)
        if existing is None:
            if not create_missing:
                raise ValueError(f"AI demo analyst profile is missing: {analyst_id}")
            rows.append(service.sync(request))
            continue
        if (
            existing.specializations != specializations
            or existing.regions != regions
            or existing.max_active_cases != 10
            or str(existing.accuracy_rate) != str(request.accuracy_rate)
            or not existing.is_active
        ):
            raise ValueError(f"AI demo analyst profile conflict: {analyst_id}")
        rows.append(AnalystProfileRead.model_validate(existing).model_dump(mode="json"))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        with Session(_get_engine()) as session:
            rows = seed(session, create_missing=not args.check)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("Demo analyst seed failed due to a database error", file=sys.stderr)
        return 1
    for row in rows:
        print(f"AI analyst profile ready: {row['analyst_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

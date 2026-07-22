"""Idempotently seed three demo analyst profiles using real Identity UUIDs."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import uuid

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import _get_engine
from app.schemas.scoring import AnalystSyncRequest
from app.services.analyst_service import AnalystService


PROFILE_DEFINITIONS = (
    (
        "card_analyst_id",
        "DEMO_CARD_ANALYST_ID",
        ["CALINTI_KART"],
        ["TR", "EU"],
        "0.9200",
    ),
    (
        "account_analyst_id",
        "DEMO_ACCOUNT_ANALYST_ID",
        ["HESAP_ELE_GECIRME"],
        ["TR", "EU"],
        "0.9000",
    ),
    (
        "laundering_analyst_id",
        "DEMO_LAUNDERING_ANALYST_ID",
        ["PARA_AKLAMA"],
        ["TR", "EU", "GLOBAL"],
        "0.9400",
    ),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-analyst-id")
    parser.add_argument("--account-analyst-id")
    parser.add_argument("--laundering-analyst-id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    resolved: list[tuple[uuid.UUID, list[str], list[str], str]] = []
    for argument, environment, specializations, regions, accuracy in PROFILE_DEFINITIONS:
        raw_value = getattr(args, argument) or os.getenv(environment)
        if not raw_value:
            print(f"Missing analyst UUID: provide --{argument.replace('_', '-')} or {environment}", file=sys.stderr)
            return 1
        try:
            analyst_id = uuid.UUID(raw_value)
        except ValueError:
            print(f"Invalid analyst UUID for {environment}", file=sys.stderr)
            return 1
        resolved.append((analyst_id, specializations, regions, accuracy))

    try:
        with Session(_get_engine()) as session:
            service = AnalystService(session)
            for analyst_id, specializations, regions, accuracy in resolved:
                service.sync(
                    AnalystSyncRequest(
                        analyst_id=analyst_id,
                        specializations=specializations,
                        regions=regions,
                        active_cases=0,
                        max_active_cases=10,
                        accuracy_rate=accuracy,
                        is_active=True,
                    )
                )
                print(f"Demo analyst profile synchronized: {analyst_id}")
    except Exception:
        print("Demo analyst seed failed due to a database error", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

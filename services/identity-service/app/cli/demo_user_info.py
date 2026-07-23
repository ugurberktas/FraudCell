"""Report fixed demo account identifiers without creating or mutating data."""
from __future__ import annotations

import json
import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli.seed_demo_users import DEMO_STAFF
from app.db.session import _get_engine
from app.models.user import User
from app.schemas.customer import normalize_turkish_gsm


def lookup(session: Session) -> dict[str, dict[str, str]]:
    emails = [item[2] for item in DEMO_STAFF]
    gsm = normalize_turkish_gsm(os.getenv("DEMO_CUSTOMER_GSM", "05550000001"))
    users = list(session.scalars(select(User).where((User.email.in_(emails)) | (User.gsm == gsm))))
    result: dict[str, dict[str, str]] = {}
    for user in users:
        key = "customer" if user.gsm == gsm else user.email
        result[key] = {"id": str(user.id), "role": user.role.value}
        if key == "customer":
            result[key]["gsm"] = gsm
    return result


def main() -> int:
    try:
        with Session(_get_engine()) as session:
            result = lookup(session)
    except Exception:
        print("Demo user lookup failed", file=sys.stderr)
        return 1
    print("DEMO_USERS_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

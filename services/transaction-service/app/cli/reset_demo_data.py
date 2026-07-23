"""Delete operational data belonging only to the supplied demo customer UUID."""
from __future__ import annotations

import json
import os
import sys
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import _get_engine
from app.models import CaseHistory, CustomerFeedback, OutboxEvent, RiskCase, Transaction


def _customer_id() -> uuid.UUID:
    raw = os.getenv("DEMO_CUSTOMER_ID", "")
    if not raw:
        raise ValueError("Missing DEMO_CUSTOMER_ID")
    return uuid.UUID(raw)


def reset(session: Session, customer_id: uuid.UUID) -> dict:
    transaction_ids = set(session.scalars(select(Transaction.id).where(Transaction.customer_id == customer_id)))
    case_ids = set(session.scalars(select(RiskCase.id).where(RiskCase.transaction_id.in_(transaction_ids)))) if transaction_ids else set()
    event_rows = list(session.scalars(select(OutboxEvent)))
    removed_event_ids: list[str] = []
    for row in event_rows:
        data = row.payload.get("payload", {}) if isinstance(row.payload, dict) else {}
        if (
            str(data.get("customer_id", "")) == str(customer_id)
            or str(data.get("transaction_id", "")) in {str(value) for value in transaction_ids}
            or str(data.get("case_id", "")) in {str(value) for value in case_ids}
        ):
            removed_event_ids.append(str(row.event_id))
            session.delete(row)
    if case_ids:
        session.execute(delete(CustomerFeedback).where(CustomerFeedback.case_id.in_(case_ids)))
        session.execute(delete(CaseHistory).where(CaseHistory.case_id.in_(case_ids)))
        session.execute(delete(RiskCase).where(RiskCase.id.in_(case_ids)))
    if transaction_ids:
        session.execute(delete(Transaction).where(Transaction.id.in_(transaction_ids)))
    session.commit()
    return {
        "transactions": len(transaction_ids),
        "cases": len(case_ids),
        "event_ids": removed_event_ids,
    }


def main() -> int:
    try:
        with Session(_get_engine()) as session:
            result = reset(session, _customer_id())
    except Exception as exc:
        print(f"Transaction demo reset failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print("DEMO_RESET_JSON=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

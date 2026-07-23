"""Response projections with dynamic SLA fields."""
from datetime import datetime, timezone
import math

from app.models import RiskCase, Transaction
from app.schemas.transaction import CaseHistoryRead, FeedbackRead, RiskCaseRead, TransactionRead


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def transaction_to_data(transaction: Transaction) -> dict:
    return TransactionRead.model_validate(transaction).model_dump(mode="json")


def case_to_data(
    risk_case: RiskCase,
    *,
    now: datetime | None = None,
    include_transaction: bool = True,
) -> dict:
    current_time = _aware_utc(now or datetime.now(timezone.utc))
    due_at = _aware_utc(risk_case.sla_due_at)
    decided_at = _aware_utc(risk_case.decided_at) if risk_case.decided_at else None
    comparison_time = decided_at or current_time
    remaining = None
    if decided_at is None:
        remaining = max(0, math.ceil((due_at - current_time).total_seconds()))

    data = RiskCaseRead(
        id=risk_case.id,
        transaction_id=risk_case.transaction_id,
        status=risk_case.status,
        assigned_analyst_id=risk_case.assigned_analyst_id,
        decision_note=risk_case.decision_note,
        customer_response=risk_case.customer_response,
        created_at=risk_case.created_at,
        assigned_at=risk_case.assigned_at,
        started_at=risk_case.started_at,
        verification_requested_at=risk_case.verification_requested_at,
        decided_at=risk_case.decided_at,
        closed_at=risk_case.closed_at,
        sla_due_at=risk_case.sla_due_at,
        sla_remaining_seconds=remaining,
        sla_exceeded=comparison_time > due_at,
        transaction=(
            TransactionRead.model_validate(risk_case.transaction)
            if include_transaction
            else None
        ),
        history=[CaseHistoryRead.model_validate(item) for item in risk_case.history],
        feedback=(FeedbackRead.model_validate(risk_case.feedback) if risk_case.feedback else None),
    )
    return data.model_dump(mode="json")

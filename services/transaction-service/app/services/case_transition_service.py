"""Central risk-case state machine."""
from datetime import datetime
import uuid

from app.common.exceptions import AppException
from app.models import CaseHistory, CaseStatus, RiskCase


ALLOWED_TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.YENI: frozenset({CaseStatus.ATANDI}),
    CaseStatus.ATANDI: frozenset({CaseStatus.INCELENIYOR}),
    CaseStatus.INCELENIYOR: frozenset(
        {
            CaseStatus.MUSTERI_DOGRULAMA,
            CaseStatus.ONAYLANDI,
            CaseStatus.BLOKLANDI,
        }
    ),
    CaseStatus.MUSTERI_DOGRULAMA: frozenset({CaseStatus.INCELENIYOR}),
    CaseStatus.ONAYLANDI: frozenset({CaseStatus.KAPANDI}),
    CaseStatus.BLOKLANDI: frozenset({CaseStatus.KAPANDI}),
    CaseStatus.KAPANDI: frozenset(),
}


class CaseTransitionService:
    def transition(
        self,
        risk_case: RiskCase,
        to_status: CaseStatus,
        *,
        actor_user_id: uuid.UUID | None,
        now: datetime,
        note: str | None = None,
    ) -> CaseHistory:
        from_status = risk_case.status
        if to_status not in ALLOWED_TRANSITIONS.get(from_status, frozenset()):
            raise AppException(
                "INVALID_CASE_TRANSITION",
                f"Case cannot transition from {from_status.value} to {to_status.value}",
                422,
                details={"from_status": from_status.value, "to_status": to_status.value},
            )

        risk_case.status = to_status
        if to_status is CaseStatus.ATANDI:
            risk_case.assigned_at = now
        elif to_status is CaseStatus.INCELENIYOR and risk_case.started_at is None:
            risk_case.started_at = now
        elif to_status is CaseStatus.MUSTERI_DOGRULAMA:
            risk_case.verification_requested_at = now
        elif to_status in {CaseStatus.ONAYLANDI, CaseStatus.BLOKLANDI}:
            risk_case.decided_at = now
        elif to_status is CaseStatus.KAPANDI:
            risk_case.closed_at = now

        history = CaseHistory(
            case_id=risk_case.id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            note=note,
            created_at=now,
        )
        risk_case.history.append(history)
        return history

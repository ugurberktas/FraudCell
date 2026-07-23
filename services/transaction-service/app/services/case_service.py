"""Risk case authorization and state-change use cases."""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session

from app.common.exceptions import AppException, NotFoundException
from app.models import CaseStatus, CustomerFeedback, CustomerResponse, TransactionDecision
from app.events import EventType, create_event
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.case_repository import CaseRepository
from app.schemas.transaction import CaseDecision
from app.services.case_transition_service import CaseTransitionService
from app.services.serializers import case_to_data


class CaseService:
    def __init__(
        self,
        session: Session,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self.session = session
        self.clock = clock
        self.repository = CaseRepository(session)
        self.transitions = CaseTransitionService()

    def list_assigned(self, analyst_id: uuid.UUID) -> list[dict]:
        return [case_to_data(item) for item in self.repository.list_assigned_to(analyst_id)]

    def list_all(self, status: CaseStatus | None = None) -> list[dict]:
        return [case_to_data(item) for item in self.repository.list_all(status)]

    def assign(
        self, case_id: uuid.UUID, analyst_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> dict:
        risk_case = self._locked_case(case_id)
        risk_case.assigned_analyst_id = analyst_id
        self.transitions.transition(
            risk_case,
            CaseStatus.ATANDI,
            actor_user_id=actor_user_id,
            now=self._now(),
            note="Manually assigned by supervisor",
        )
        return self._commit_and_render(risk_case)

    def start(self, case_id: uuid.UUID, analyst_id: uuid.UUID) -> dict:
        risk_case = self._locked_case(case_id)
        self._require_assigned(risk_case, analyst_id)
        self.transitions.transition(
            risk_case,
            CaseStatus.INCELENIYOR,
            actor_user_id=analyst_id,
            now=self._now(),
        )
        return self._commit_and_render(risk_case)

    def request_verification(self, case_id: uuid.UUID, analyst_id: uuid.UUID) -> dict:
        risk_case = self._locked_case(case_id)
        self._require_assigned(risk_case, analyst_id)
        self.transitions.transition(
            risk_case,
            CaseStatus.MUSTERI_DOGRULAMA,
            actor_user_id=analyst_id,
            now=self._now(),
        )
        return self._commit_and_render(risk_case)

    def customer_response(
        self,
        case_id: uuid.UUID,
        customer_id: uuid.UUID,
        response: CustomerResponse,
    ) -> dict:
        risk_case = self._locked_case(case_id)
        if risk_case.transaction.customer_id != customer_id:
            self.session.rollback()
            raise AppException("FORBIDDEN", "Access is forbidden", 403)
        risk_case.customer_response = response
        self.transitions.transition(
            risk_case,
            CaseStatus.INCELENIYOR,
            actor_user_id=customer_id,
            now=self._now(),
            note="Customer verification response received",
        )
        return self._commit_and_render(risk_case)

    def decide(
        self,
        case_id: uuid.UUID,
        analyst_id: uuid.UUID,
        decision: CaseDecision,
        note: str | None,
        correlation_id: str | None = None,
    ) -> dict:
        risk_case = self._locked_case(case_id)
        self._require_assigned(risk_case, analyst_id)
        if decision is CaseDecision.BLOKLANDI and not note:
            self.session.rollback()
            raise AppException(
                "DECISION_NOTE_REQUIRED",
                "A decision note is required when blocking a transaction",
                422,
            )
        target = CaseStatus(decision.value)
        risk_case.decision_note = note
        self.transitions.transition(
            risk_case,
            target,
            actor_user_id=analyst_id,
            now=self._now(),
            note=note,
        )
        if target is CaseStatus.BLOKLANDI:
            risk_case.transaction.decision = TransactionDecision.BLOK
            risk_case.transaction.temporary_blocked = True
        else:
            risk_case.transaction.decision = TransactionDecision.ONAY
        event = create_event(
            EventType.CASE_DECISION_MADE,
            "transaction-service",
            self._decision_payload(risk_case, analyst_id),
            correlation_id=correlation_id,
        )
        OutboxRepository(self.session).add_envelope(event, "case.decision_made")
        rendered = self._commit_and_render(risk_case)
        rendered["event_delivery"] = "PENDING"
        rendered["event_id"] = str(event.event_id)
        return rendered

    def close(self, case_id: uuid.UUID, actor_user_id: uuid.UUID) -> dict:
        risk_case = self._locked_case(case_id)
        self.transitions.transition(
            risk_case,
            CaseStatus.KAPANDI,
            actor_user_id=actor_user_id,
            now=self._now(),
            note="Case closed by supervisor",
        )
        return self._commit_and_render(risk_case)

    def submit_feedback(
        self,
        case_id: uuid.UUID,
        customer_id: uuid.UUID,
        rating: int,
        correlation_id: str | None = None,
    ) -> dict:
        risk_case = self._locked_case(case_id)
        if risk_case.transaction.customer_id != customer_id:
            self.session.rollback()
            raise AppException("FORBIDDEN", "Access is forbidden", 403)
        if risk_case.status is not CaseStatus.KAPANDI:
            self.session.rollback()
            raise AppException("FEEDBACK_CASE_NOT_CLOSED", "Feedback requires a closed case", 422)
        if risk_case.feedback is not None:
            self.session.rollback()
            raise AppException("FEEDBACK_ALREADY_SUBMITTED", "Feedback was already submitted", 409)
        feedback = CustomerFeedback(
            case_id=risk_case.id,
            customer_id=customer_id,
            rating=rating,
            created_at=self._now(),
        )
        self.session.add(feedback)
        self.session.flush()
        event = create_event(
            EventType.FEEDBACK_SUBMITTED,
            "transaction-service",
            {
                "feedback_id": str(feedback.id),
                "case_id": str(risk_case.id),
                "customer_id": str(customer_id),
                "rating": rating,
                "created_at": feedback.created_at.isoformat(),
            },
            correlation_id=correlation_id,
        )
        OutboxRepository(self.session).add_envelope(event, "feedback.submitted")
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return {
            "id": str(feedback.id),
            "case_id": str(case_id),
            "rating": feedback.rating,
            "created_at": feedback.created_at.isoformat(),
            "event_delivery": "PENDING",
            "event_id": str(event.event_id),
        }

    @staticmethod
    def _decision_payload(risk_case, analyst_id: uuid.UUID) -> dict:
        decided_at = risk_case.decided_at
        created_at = risk_case.created_at
        due_at = risk_case.sla_due_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if decided_at.tzinfo is None:
            decided_at = decided_at.replace(tzinfo=timezone.utc)
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        return {
            "case_id": str(risk_case.id),
            "transaction_id": str(risk_case.transaction_id),
            "analyst_id": str(analyst_id),
            "decision": risk_case.status.value,
            "fraud_type": risk_case.transaction.fraud_type.value,
            "risk_level": risk_case.transaction.risk_level.value,
            "customer_response": (
                risk_case.customer_response.value
                if risk_case.customer_response is not None
                else CustomerResponse.YANIT_YOK.value
            ),
            "case_created_at": created_at.isoformat(),
            "decided_at": decided_at.isoformat(),
            "resolution_seconds": max(0, int((decided_at - created_at).total_seconds())),
            "sla_exceeded": decided_at > due_at,
            "is_false_positive": False,
        }

    def _locked_case(self, case_id: uuid.UUID):
        risk_case = self.repository.get_by_id(case_id, for_update=True)
        if risk_case is None:
            raise NotFoundException("Risk case not found")
        return risk_case

    def _require_assigned(self, risk_case, analyst_id: uuid.UUID) -> None:
        if risk_case.assigned_analyst_id != analyst_id:
            self.session.rollback()
            raise AppException("FORBIDDEN", "Access is forbidden", 403)

    def _now(self) -> datetime:
        value = self.clock()
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    def _commit_and_render(self, risk_case) -> dict:
        try:
            self.session.commit()
            stored = self.repository.get_by_id(risk_case.id)
            if stored is None:
                raise RuntimeError("Committed risk case could not be reloaded")
            return case_to_data(stored, now=self._now())
        except Exception:
            self.session.rollback()
            raise

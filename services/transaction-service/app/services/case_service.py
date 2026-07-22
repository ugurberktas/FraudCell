"""Risk case authorization and state-change use cases."""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session

from app.common.exceptions import AppException, NotFoundException
from app.models import CaseStatus, CustomerResponse, TransactionDecision
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
        return self._commit_and_render(risk_case)

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

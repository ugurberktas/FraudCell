"""Transaction golden-path orchestration."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

from sqlalchemy.orm import Session

from app.clients.ai_client import AIClient, AIServiceUnavailable
from app.common.exceptions import AppException, NotFoundException
from app.models import (
    AIStatus,
    CaseHistory,
    CaseStatus,
    FraudType,
    RiskCase,
    RiskLevel,
    Transaction,
    TransactionDecision,
)
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.ai import AIScoringResult
from app.schemas.transaction import TransactionCreate
from app.security.tokens import AuthenticatedUser, UserRole
from app.services.serializers import case_to_data, transaction_to_data
from app.services.case_transition_service import CaseTransitionService


SLA_DURATIONS = {
    RiskLevel.KRITIK: timedelta(minutes=15),
    RiskLevel.YUKSEK: timedelta(hours=1),
    RiskLevel.ORTA: timedelta(hours=4),
    RiskLevel.DUSUK: timedelta(hours=24),
    RiskLevel.BELIRSIZ: timedelta(hours=1),
}


class TransactionService:
    def __init__(
        self,
        session: Session,
        ai_client: AIClient,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self.session = session
        self.ai_client = ai_client
        self.clock = clock
        self.repository = TransactionRepository(session)

    def create(
        self,
        payload: TransactionCreate,
        *,
        customer_id: uuid.UUID,
        request_id: str,
    ) -> dict:
        transaction_id = uuid.uuid4()
        ai_fallback = False
        try:
            ai_result = self.ai_client.score_and_assign(
                transaction_id=transaction_id,
                customer_id=customer_id,
                transaction=payload,
                request_id=request_id,
            )
        except AIServiceUnavailable:
            ai_fallback = True
            ai_result = None

        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        try:
            transaction_number = self.repository.next_transaction_number(now)
            values = self._scoring_values(ai_result)
            transaction = Transaction(
                id=transaction_id,
                transaction_number=transaction_number,
                customer_id=customer_id,
                amount=payload.amount,
                transaction_type=payload.transaction_type,
                recipient=payload.recipient,
                source_device=payload.source_device,
                city=payload.city,
                occurred_at=payload.occurred_at,
                risk_score=values["risk_score"],
                fraud_type=values["fraud_type"],
                decision=values["decision"],
                risk_level=values["risk_level"],
                ai_status=(AIStatus.UNAVAILABLE if ai_fallback else AIStatus.SCORED),
                model_version=values["model_version"],
                temporary_blocked=(
                    values["decision"] is TransactionDecision.BLOK
                    or (
                        values["risk_score"] is not None
                        and values["risk_score"] > Decimal("0.9")
                    )
                ),
                created_at=now,
                updated_at=now,
            )
            self.repository.add(transaction)

            create_case = (
                ai_fallback
                or values["decision"] is not TransactionDecision.ONAY
                or values["risk_level"] is not RiskLevel.DUSUK
            )
            if create_case:
                assigned_analyst_id = values["assigned_analyst_id"]
                risk_case = RiskCase(
                    id=uuid.uuid4(),
                    transaction=transaction,
                    status=CaseStatus.YENI,
                    assigned_analyst_id=assigned_analyst_id,
                    created_at=now,
                    sla_due_at=now + SLA_DURATIONS[values["risk_level"]],
                )
                transaction.risk_case = risk_case
                self.session.add(risk_case)
                risk_case.history.append(
                    CaseHistory(
                        case_id=risk_case.id,
                        from_status=None,
                        to_status=CaseStatus.YENI,
                        actor_user_id=None,
                        note="Risk case created from AI scoring",
                        created_at=now,
                    )
                )
                if assigned_analyst_id is not None:
                    CaseTransitionService().transition(
                        risk_case,
                        CaseStatus.ATANDI,
                        actor_user_id=None,
                        now=now + timedelta(microseconds=1),
                        note="Assigned by AI scoring",
                    )

            self.session.commit()
            stored = self.repository.get_by_id(transaction_id)
            if stored is None:
                raise RuntimeError("Committed transaction could not be reloaded")
            return {
                "transaction": transaction_to_data(stored),
                "case": (
                    case_to_data(stored.risk_case, now=now)
                    if stored.risk_case is not None
                    else None
                ),
                "ai_result": self._ai_response(ai_result),
                "ai_fallback": ai_fallback,
            }
        except Exception:
            self.session.rollback()
            raise

    def list_for_customer(self, customer_id: uuid.UUID) -> list[dict]:
        return [
            {
                "transaction": transaction_to_data(item),
                "case": case_to_data(item.risk_case) if item.risk_case else None,
            }
            for item in self.repository.list_for_customer(customer_id)
        ]

    def get_for_user(
        self, transaction_id: uuid.UUID, user: AuthenticatedUser
    ) -> dict:
        transaction = self.repository.get_by_id(transaction_id)
        if transaction is None:
            raise NotFoundException("Transaction not found")
        allowed = False
        if user.role is UserRole.CUSTOMER:
            allowed = transaction.customer_id == user.user_id
        elif user.role is UserRole.ANALYST:
            allowed = (
                transaction.risk_case is not None
                and transaction.risk_case.assigned_analyst_id == user.user_id
            )
        elif user.role in {UserRole.SUPERVISOR, UserRole.ADMIN}:
            allowed = True
        if not allowed:
            raise AppException("FORBIDDEN", "Access is forbidden", 403)
        return {
            "transaction": transaction_to_data(transaction),
            "case": case_to_data(transaction.risk_case) if transaction.risk_case else None,
        }

    @staticmethod
    def _scoring_values(ai_result: AIScoringResult | None) -> dict:
        if ai_result is None:
            return {
                "risk_score": None,
                "fraud_type": FraudType.TEMIZ,
                "decision": TransactionDecision.INCELEME,
                "risk_level": RiskLevel.BELIRSIZ,
                "model_version": None,
                "assigned_analyst_id": None,
            }
        return ai_result.model_dump()

    @staticmethod
    def _ai_response(ai_result: AIScoringResult | None) -> dict:
        if ai_result is None:
            return {
                "status": AIStatus.UNAVAILABLE.value,
                "risk_score": None,
                "fraud_type": FraudType.TEMIZ.value,
                "decision": TransactionDecision.INCELEME.value,
                "risk_level": RiskLevel.BELIRSIZ.value,
                "model_version": None,
                "assigned_analyst_id": None,
                "risk_reasons": ["AI service unavailable"],
                "assignment_status": "QUEUED",
                "assignment_score": None,
                "message": "AI unavailable; manual review case created",
            }
        data = ai_result.model_dump(mode="json")
        data["status"] = AIStatus.SCORED.value
        return data

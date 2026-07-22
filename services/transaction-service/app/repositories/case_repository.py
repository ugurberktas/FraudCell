"""Persistence operations for risk cases and their history."""
from __future__ import annotations

import uuid

from sqlalchemy import case as sql_case
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import CaseHistory, CaseStatus, RiskCase, RiskLevel, Transaction


class CaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _load_options():
        return (
            selectinload(RiskCase.transaction),
            selectinload(RiskCase.history),
        )

    def add(self, risk_case: RiskCase) -> RiskCase:
        self.session.add(risk_case)
        return risk_case

    def add_history(self, history: CaseHistory) -> CaseHistory:
        self.session.add(history)
        return history

    def get_by_id(self, case_id: uuid.UUID, *, for_update: bool = False) -> RiskCase | None:
        statement = select(RiskCase).where(RiskCase.id == case_id)
        if for_update:
            statement = statement.with_for_update()
        risk_case = self.session.scalar(statement)
        if risk_case is None:
            return None
        # Load after row locking so PostgreSQL never tries to lock an outer join.
        _ = risk_case.transaction
        _ = risk_case.history
        return risk_case

    def list_assigned_to(self, analyst_id: uuid.UUID) -> list[RiskCase]:
        priority = sql_case(
            (Transaction.risk_level == RiskLevel.KRITIK, 0),
            (Transaction.risk_level == RiskLevel.YUKSEK, 1),
            (Transaction.risk_level == RiskLevel.ORTA, 2),
            (Transaction.risk_level == RiskLevel.BELIRSIZ, 3),
            else_=4,
        )
        statement = (
            select(RiskCase)
            .join(RiskCase.transaction)
            .where(RiskCase.assigned_analyst_id == analyst_id)
            .options(*self._load_options())
            .order_by(priority, RiskCase.sla_due_at.asc())
        )
        return list(self.session.scalars(statement))

    def list_all(self, status: CaseStatus | None = None) -> list[RiskCase]:
        statement = select(RiskCase).options(*self._load_options())
        if status is not None:
            statement = statement.where(RiskCase.status == status)
        statement = statement.order_by(RiskCase.created_at.desc())
        return list(self.session.scalars(statement))

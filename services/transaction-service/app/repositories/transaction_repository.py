"""Persistence operations for transactions."""
from datetime import datetime
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.common.exceptions import AppException
from app.models import RiskCase, Transaction


class TransactionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def next_transaction_number(self, occurred_at: datetime) -> str:
        year = occurred_at.year
        next_value = self.session.execute(
            text(
                """
                INSERT INTO transaction_number_sequences (year, last_value)
                VALUES (:year, 1)
                ON CONFLICT (year)
                DO UPDATE SET last_value = transaction_number_sequences.last_value + 1
                RETURNING last_value
                """
            ),
            {"year": year},
        ).scalar_one()
        if next_value > 999_999:
            raise AppException(
                "TRANSACTION_NUMBER_EXHAUSTED",
                "Transaction number capacity is exhausted for the current year",
                503,
            )
        return f"TRX-{year:04d}-{next_value:06d}"

    def add(self, transaction: Transaction) -> Transaction:
        self.session.add(transaction)
        return transaction

    def get_by_id(self, transaction_id: uuid.UUID) -> Transaction | None:
        statement = (
            select(Transaction)
            .where(Transaction.id == transaction_id)
            .options(
                selectinload(Transaction.risk_case).selectinload(RiskCase.history),
                selectinload(Transaction.risk_case).selectinload(RiskCase.feedback),
            )
        )
        return self.session.scalar(statement)

    def list_for_customer(self, customer_id: uuid.UUID) -> list[Transaction]:
        statement = (
            select(Transaction)
            .where(Transaction.customer_id == customer_id)
            .options(
                selectinload(Transaction.risk_case).selectinload(RiskCase.history),
                selectinload(Transaction.risk_case).selectinload(RiskCase.feedback),
            )
            .order_by(Transaction.created_at.desc())
        )
        return list(self.session.scalars(statement))

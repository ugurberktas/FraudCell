"""Append-only AuditLog persistence and filtered reads."""
from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        actor_user_id: uuid.UUID | None,
        action: str,
        ip_address: str | None,
        result: str,
        resource_type: str | None,
        resource_id: str | None,
        details: dict | list | None,
    ) -> AuditLog:
        record = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            ip_address=ip_address,
            result=result,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )
        self.session.add(record)
        self.session.flush([record])
        return record

    def list_filtered(
        self,
        *,
        page: int,
        page_size: int,
        action: str | None,
        actor_user_id: uuid.UUID | None,
        result: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> tuple[list[AuditLog], int]:
        conditions = []
        if action is not None:
            conditions.append(AuditLog.action == action)
        if actor_user_id is not None:
            conditions.append(AuditLog.actor_user_id == actor_user_id)
        if result is not None:
            conditions.append(AuditLog.result == result)
        if date_from is not None:
            conditions.append(AuditLog.created_at >= date_from)
        if date_to is not None:
            conditions.append(AuditLog.created_at <= date_to)

        total = self.session.scalar(
            select(func.count(AuditLog.id)).where(*conditions)
        ) or 0
        statement = (
            select(AuditLog)
            .where(*conditions)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.scalars(statement).all()), total

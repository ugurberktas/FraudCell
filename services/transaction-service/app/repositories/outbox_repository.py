"""Transactional outbox persistence operations."""
from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events import EventEnvelope
from app.models import OutboxEvent


class OutboxRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_envelope(self, envelope: EventEnvelope, routing_key: str) -> OutboxEvent:
        row = OutboxEvent(
            event_id=envelope.event_id,
            event_type=envelope.event_type.value,
            routing_key=routing_key,
            payload=envelope.model_dump(mode="json"),
        )
        self.session.add(row)
        return row

    def next_pending(self) -> OutboxEvent | None:
        return self.session.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )

    def mark_published(self, row: OutboxEvent) -> None:
        row.published_at = datetime.now(timezone.utc)
        row.last_error = None

    def mark_failed(self, row: OutboxEvent, error_kind: str) -> None:
        row.attempts += 1
        row.last_error = error_kind[:500]

    def get_by_event_id(self, event_id: uuid.UUID) -> OutboxEvent | None:
        return self.session.scalar(
            select(OutboxEvent).where(OutboxEvent.event_id == event_id)
        )

"""Event envelope model and helper utilities."""
from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field, field_validator

from app.events.types import EventType


class EventEnvelope(BaseModel):
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: EventType
    event_version: int = Field(default=1, gt=0)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    producer: str
    correlation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at", mode="after")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("occurred_at datetime must be timezone-aware (e.g. UTC)")
        return v


def create_event(
    event_type: EventType | str,
    producer: str,
    payload: dict[str, Any],
    correlation_id: Optional[uuid.UUID | str] = None,
    event_version: int = 1,
) -> EventEnvelope:
    """Helper function to create an EventEnvelope instance.

    Validates correlation_id string or generates a new UUID v4 if invalid.
    """
    valid_correlation_id: uuid.UUID
    if correlation_id is not None:
        if isinstance(correlation_id, uuid.UUID):
            valid_correlation_id = correlation_id
        else:
            try:
                valid_correlation_id = uuid.UUID(str(correlation_id))
            except (ValueError, TypeError):
                valid_correlation_id = uuid.uuid4()
    else:
        valid_correlation_id = uuid.uuid4()

    if isinstance(event_type, str):
        event_type = EventType(event_type)

    return EventEnvelope(
        event_type=event_type,
        producer=producer,
        payload=payload,
        correlation_id=valid_correlation_id,
        event_version=event_version,
    )

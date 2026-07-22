"""Tests for EventEnvelope models and validation rules."""
from datetime import datetime, timezone
import json
import uuid
import pytest
from pydantic import ValidationError

from app.events.envelope import EventEnvelope, create_event
from app.events.types import EventType


def test_valid_event_creation() -> None:
    event = EventEnvelope(
        event_type=EventType.TRANSACTION_CREATED,
        producer="transaction-service",
        payload={"amount": 100},
    )
    assert isinstance(event.event_id, uuid.UUID)
    assert event.event_type == EventType.TRANSACTION_CREATED
    assert event.event_version == 1
    assert isinstance(event.occurred_at, datetime)
    assert event.occurred_at.tzinfo == timezone.utc
    assert event.producer == "transaction-service"
    assert isinstance(event.correlation_id, uuid.UUID)
    assert event.payload == {"amount": 100}


def test_auto_event_id_is_uuid4() -> None:
    event1 = EventEnvelope(event_type=EventType.TRANSACTION_CREATED, producer="transaction-service")
    event2 = EventEnvelope(event_type=EventType.TRANSACTION_CREATED, producer="transaction-service")
    assert isinstance(event1.event_id, uuid.UUID)
    assert event1.event_id.version == 4
    assert event1.event_id != event2.event_id


def test_auto_occurred_at_is_utc() -> None:
    event = EventEnvelope(event_type=EventType.TRANSACTION_CREATED, producer="transaction-service")
    assert event.occurred_at.tzinfo is not None
    assert event.occurred_at.tzinfo == timezone.utc


def test_invalid_event_type_rejected() -> None:
    with pytest.raises(ValidationError):
        EventEnvelope(
            event_type="invalid.event.type",  # type: ignore
            producer="transaction-service",
        )


def test_event_version_zero_or_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        EventEnvelope(
            event_type=EventType.TRANSACTION_CREATED,
            producer="transaction-service",
            event_version=0,
        )

    with pytest.raises(ValidationError):
        EventEnvelope(
            event_type=EventType.TRANSACTION_CREATED,
            producer="transaction-service",
            event_version=-1,
        )


def test_naive_datetime_rejected() -> None:
    naive_dt = datetime(2026, 7, 22, 23, 50, 0)
    with pytest.raises(ValidationError):
        EventEnvelope(
            event_type=EventType.TRANSACTION_CREATED,
            producer="transaction-service",
            occurred_at=naive_dt,
        )


def test_json_roundtrip_serialization() -> None:
    event = EventEnvelope(
        event_type=EventType.TRANSACTION_CREATED,
        producer="transaction-service",
        payload={"amount": 100},
    )
    json_str = event.model_dump_json()
    assert isinstance(json_str, str)
    deserialized = EventEnvelope.model_validate_json(json_str)

    assert deserialized.event_id == event.event_id
    assert deserialized.event_type == event.event_type
    assert deserialized.producer == event.producer
    assert deserialized.correlation_id == event.correlation_id
    assert deserialized.payload == event.payload


def test_create_event_correlation_id_handling() -> None:
    # 1. Valid UUID string
    valid_uuid_str = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    ev1 = create_event(
        event_type="transaction.created",
        producer="transaction-service",
        payload={"test": 1},
        correlation_id=valid_uuid_str,
    )
    assert str(ev1.correlation_id) == valid_uuid_str

    # 2. UUID instance
    uuid_obj = uuid.uuid4()
    ev2 = create_event(
        event_type=EventType.TRANSACTION_CREATED,
        producer="transaction-service",
        payload={"test": 2},
        correlation_id=uuid_obj,
    )
    assert ev2.correlation_id == uuid_obj

    # 3. Invalid correlation_id fallback to valid UUID v4
    ev3 = create_event(
        event_type="transaction.created",
        producer="transaction-service",
        payload={"test": 3},
        correlation_id="not-a-valid-uuid",
    )
    assert isinstance(ev3.correlation_id, uuid.UUID)
    assert ev3.correlation_id.version == 4

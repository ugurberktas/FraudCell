from pathlib import Path
import uuid

from sqlalchemy import func, select

from app.models import OutboxEvent
from app.workers import outbox_publisher
from tests.conftest import auth
from tests.test_golden_path import create_transaction


def _started_case(client, fake_ai):
    analyst = uuid.uuid4()
    fake_ai.result = fake_ai.result.model_copy(update={"assigned_analyst_id": analyst})
    case_id = create_transaction(client, uuid.uuid4()).json()["data"]["case"]["id"]
    client.post(f"/cases/{case_id}/start", headers=auth(analyst, "ANALYST"))
    return case_id, analyst


def test_decision_and_outbox_are_committed_together(client, fake_ai, db):
    case_id, analyst = _started_case(client, fake_ai)
    response = client.post(
        f"/cases/{case_id}/decision",
        json={"decision": "ONAYLANDI"},
        headers={**auth(analyst, "ANALYST"), "X-Request-ID": str(uuid.uuid4())},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["event_delivery"] == "PENDING"
    row = db.scalar(select(OutboxEvent).where(OutboxEvent.event_id == uuid.UUID(data["event_id"])))
    assert row is not None and row.published_at is None
    assert row.payload["event_type"] == "case.decision_made"
    assert row.payload["payload"]["case_id"] == case_id


def test_failed_decision_does_not_create_outbox(client, fake_ai, db):
    case_id, analyst = _started_case(client, fake_ai)
    response = client.post(
        f"/cases/{case_id}/decision",
        json={"decision": "BLOKLANDI"},
        headers=auth(analyst, "ANALYST"),
    )
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 0


def test_second_case_decision_does_not_create_second_event(client, fake_ai, db):
    case_id, analyst = _started_case(client, fake_ai)
    path = f"/cases/{case_id}/decision"
    assert client.post(path, json={"decision": "ONAYLANDI"}, headers=auth(analyst, "ANALYST")).status_code == 200
    assert client.post(path, json={"decision": "ONAYLANDI"}, headers=auth(analyst, "ANALYST")).status_code == 422
    assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1


def test_event_payload_has_required_fields_and_no_sensitive_data(client, fake_ai, db):
    case_id, analyst = _started_case(client, fake_ai)
    client.post(f"/cases/{case_id}/decision", json={"decision": "ONAYLANDI"}, headers=auth(analyst, "ANALYST"))
    payload = db.scalar(select(OutboxEvent)).payload
    data = payload["payload"]
    assert set(data) == {
        "case_id", "transaction_id", "analyst_id", "decision", "fraud_type",
        "risk_level", "customer_response", "case_created_at", "decided_at",
        "resolution_seconds", "sla_exceeded", "is_false_positive",
    }
    serialized = str(payload).lower()
    assert all(word not in serialized for word in ("password", "token", "otp", "email"))


def test_publisher_marks_event_published(monkeypatch, engine, db):
    row = OutboxEvent(event_id=uuid.uuid4(), event_type="case.decision_made", routing_key="case.decision_made", payload={"event_id": str(uuid.uuid4())})
    db.add(row)
    db.commit()
    monkeypatch.setattr(outbox_publisher, "_get_engine", lambda: engine)

    class FakePublisher:
        def publish(self, routing_key, payload):
            assert routing_key == "case.decision_made"

    assert outbox_publisher.publish_one(FakePublisher()) is True
    db.expire_all()
    assert db.get(OutboxEvent, row.id).published_at is not None


def test_publish_failure_keeps_pending_and_records_safe_error(monkeypatch, engine, db):
    row = OutboxEvent(event_id=uuid.uuid4(), event_type="case.decision_made", routing_key="case.decision_made", payload={})
    db.add(row)
    db.commit()
    monkeypatch.setattr(outbox_publisher, "_get_engine", lambda: engine)

    class FailedPublisher:
        def publish(self, *_):
            raise ConnectionError("amqp://user:secret@rabbit")

    try:
        outbox_publisher.publish_one(FailedPublisher())
    except ConnectionError:
        pass
    db.expire_all()
    stored = db.get(OutboxEvent, row.id)
    assert stored.published_at is None and stored.attempts == 1
    assert stored.last_error == "ConnectionError" and "secret" not in stored.last_error


def test_outbox_migration_has_upgrade_and_downgrade():
    text = (Path(__file__).parents[1] / "alembic/versions/002_transactional_outbox.py").read_text()
    assert "def upgrade()" in text and "def downgrade()" in text

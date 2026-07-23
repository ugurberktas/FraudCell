from sqlalchemy import func, select
import uuid

from app.cli.reset_demo_data import reset as reset_demo_data
from app.models import CaseStatus, CustomerFeedback, OutboxEvent, RiskCase, Transaction
from tests.conftest import auth
from tests.test_golden_path import create_transaction


def _decided_case(client, fake_ai, customer, analyst):
    fake_ai.result = fake_ai.result.model_copy(update={"assigned_analyst_id": analyst})
    case_id = create_transaction(client, customer).json()["data"]["case"]["id"]
    client.post(f"/cases/{case_id}/start", headers=auth(analyst, "ANALYST"))
    client.post(
        f"/cases/{case_id}/decision",
        json={"decision": "ONAYLANDI"},
        headers=auth(analyst, "ANALYST"),
    )
    return case_id


def _closed_case(client, fake_ai, customer, analyst):
    case_id = _decided_case(client, fake_ai, customer, analyst)
    response = client.post(
        f"/cases/{case_id}/close", headers=auth(uuid.uuid4(), "SUPERVISOR")
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "KAPANDI"
    return case_id


def test_feedback_rating_validation(client):
    for rating in (0, 6):
        response = client.post(
            f"/cases/{uuid.uuid4()}/feedback",
            json={"rating": rating},
            headers=auth(uuid.uuid4(), "CUSTOMER"),
        )
        assert response.status_code == 422


def test_feedback_requires_closed_case(client, fake_ai):
    customer, analyst = uuid.uuid4(), uuid.uuid4()
    case_id = _decided_case(client, fake_ai, customer, analyst)
    response = client.post(
        f"/cases/{case_id}/feedback", json={"rating": 5}, headers=auth(customer, "CUSTOMER")
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FEEDBACK_CASE_NOT_CLOSED"


def test_feedback_ownership_single_submission_and_outbox(client, fake_ai, db):
    customer, analyst = uuid.uuid4(), uuid.uuid4()
    case_id = _closed_case(client, fake_ai, customer, analyst)
    denied = client.post(
        f"/cases/{case_id}/feedback",
        json={"rating": 5},
        headers=auth(uuid.uuid4(), "CUSTOMER"),
    )
    assert denied.status_code == 403
    response = client.post(
        f"/cases/{case_id}/feedback",
        json={"rating": 5},
        headers={**auth(customer, "CUSTOMER"), "X-Request-ID": str(uuid.uuid4())},
    )
    assert response.status_code == 201
    assert response.json()["data"]["event_delivery"] == "PENDING"
    duplicate = client.post(
        f"/cases/{case_id}/feedback", json={"rating": 4}, headers=auth(customer, "CUSTOMER")
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "FEEDBACK_ALREADY_SUBMITTED"
    assert db.scalar(select(func.count()).select_from(CustomerFeedback)) == 1
    event = db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "feedback.submitted"))
    assert event.payload["payload"]["case_id"] == case_id
    assert event.payload["payload"]["rating"] == 5
    assert "password" not in str(event.payload).lower()


def test_feedback_appears_in_customer_history(client, fake_ai):
    customer, analyst = uuid.uuid4(), uuid.uuid4()
    case_id = _closed_case(client, fake_ai, customer, analyst)
    client.post(f"/cases/{case_id}/feedback", json={"rating": 3}, headers=auth(customer, "CUSTOMER"))
    items = client.get("/transactions/me", headers=auth(customer, "CUSTOMER")).json()["data"]["items"]
    assert items[0]["case"]["feedback"]["rating"] == 3


def test_invalid_close_transition_does_not_change_case(client, fake_ai, db):
    fake_ai.unavailable = True
    case_id = create_transaction(client, uuid.uuid4()).json()["data"]["case"]["id"]
    response = client.post(f"/cases/{case_id}/close", headers=auth(uuid.uuid4(), "SUPERVISOR"))
    assert response.status_code == 422
    assert db.get(RiskCase, uuid.UUID(case_id)).status is CaseStatus.YENI


def test_demo_reset_deletes_only_demo_customer_data_and_is_idempotent(client, fake_ai, db):
    demo_customer, real_customer = uuid.uuid4(), uuid.uuid4()
    analyst = uuid.uuid4()
    demo_case = _closed_case(client, fake_ai, demo_customer, analyst)
    client.post(f"/cases/{demo_case}/feedback", json={"rating": 5}, headers=auth(demo_customer, "CUSTOMER"))
    real_transaction = create_transaction(client, real_customer).json()["data"]["transaction"]["id"]
    first = reset_demo_data(db, demo_customer)
    second = reset_demo_data(db, demo_customer)
    assert first["transactions"] == 1 and first["cases"] == 1
    assert len(first["event_ids"]) == 2
    assert second == {"transactions": 0, "cases": 0, "event_ids": []}
    assert db.get(Transaction, uuid.UUID(real_transaction)) is not None
    assert db.scalar(select(func.count()).select_from(CustomerFeedback)) == 0

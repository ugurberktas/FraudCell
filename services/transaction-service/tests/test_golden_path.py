from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
from pathlib import Path
import re
import uuid

from sqlalchemy import inspect, select

from app.clients.ai_client import get_ai_client
from app.db.base import Base
from app.main import app
from app.models import (
    CaseHistory,
    CaseStatus,
    FraudType,
    RiskCase,
    RiskLevel,
    Transaction,
    TransactionDecision,
)
from app.schemas.ai import AIScoringResult
from app.services.case_transition_service import CaseTransitionService
from tests.conftest import FakeAIClient, auth, transaction_payload


def create_transaction(client, authenticated_customer_id, **payload_overrides):
    return client.post(
        "/transactions",
        json=transaction_payload(**payload_overrides),
        headers=auth(authenticated_customer_id, "CUSTOMER"),
    )


def test_models_create_expected_tables_and_migration_has_upgrade_downgrade(engine):
    tables = set(inspect(engine).get_table_names())
    assert {
        "transactions",
        "transaction_number_sequences",
        "risk_cases",
        "case_history",
    } <= tables

    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "001_initial_transaction_schema.py"
    )
    spec = importlib.util.spec_from_file_location("transaction_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert callable(module.upgrade)
    assert callable(module.downgrade)


def test_customer_creates_decimal_transaction_with_unique_readable_numbers(client, db):
    customer_id = uuid.uuid4()
    first = create_transaction(client, customer_id)
    second = create_transaction(client, customer_id, amount=10.25)
    assert first.status_code == second.status_code == 201
    first_number = first.json()["data"]["transaction"]["transaction_number"]
    second_number = second.json()["data"]["transaction"]["transaction_number"]
    assert re.fullmatch(r"TRX-\d{4}-\d{6}", first_number)
    assert first_number != second_number
    stored = db.scalar(select(Transaction).where(Transaction.transaction_number == first_number))
    assert stored.amount == Decimal("48500.00")


def test_customer_id_cannot_be_injected_from_body(client):
    customer_id = uuid.uuid4()
    response = create_transaction(client, customer_id, customer_id=str(uuid.uuid4()))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_ai_success_fields_are_persisted_and_request_id_forwarded(client, fake_ai, db):
    analyst_id = uuid.uuid4()
    fake_ai.result = AIScoringResult(
        risk_score="0.94",
        fraud_type=FraudType.HESAP_ELE_GECIRME,
        decision=TransactionDecision.INCELEME,
        risk_level=RiskLevel.KRITIK,
        model_version="golden-v2",
        assigned_analyst_id=analyst_id,
    )
    response = client.post(
        "/transactions",
        json=transaction_payload(),
        headers={**auth(uuid.uuid4(), "CUSTOMER"), "X-Request-ID": "golden-request-42"},
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["ai_fallback"] is False
    assert data["transaction"]["risk_score"] == "0.94000"
    assert data["transaction"]["model_version"] == "golden-v2"
    assert data["case"]["assigned_analyst_id"] == str(analyst_id)
    assert data["case"]["status"] == "ATANDI"
    assert [item["to_status"] for item in data["case"]["history"]] == [
        "YENI",
        "ATANDI",
    ]
    assert data["case"]["history"][0]["from_status"] is None
    assert data["case"]["history"][1]["from_status"] == "YENI"
    assert fake_ai.request_ids == ["golden-request-42"]
    assert response.headers["X-Request-ID"] == "golden-request-42"


def test_ai_failure_still_returns_201_and_creates_manual_case(client, fake_ai, db):
    fake_ai.unavailable = True
    response = create_transaction(client, uuid.uuid4())
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["ai_fallback"] is True
    assert data["transaction"]["ai_status"] == "UNAVAILABLE"
    assert data["transaction"]["risk_score"] is None
    assert data["transaction"]["risk_level"] == "BELIRSIZ"
    assert data["transaction"]["decision"] == "INCELEME"
    assert data["case"]["status"] == "YENI"
    assert data["case"]["assigned_analyst_id"] is None
    assert "manual review" in data["ai_result"]["message"]


def test_low_risk_approved_transaction_has_no_case(client, fake_ai, db):
    fake_ai.result = AIScoringResult(
        risk_score="0.08",
        fraud_type=FraudType.TEMIZ,
        decision=TransactionDecision.ONAY,
        risk_level=RiskLevel.DUSUK,
        model_version="golden-v1",
    )
    response = create_transaction(client, uuid.uuid4())
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["case"] is None
    assert db.scalar(select(RiskCase)) is None


def test_review_and_block_decisions_create_cases(client, fake_ai):
    customer_id = uuid.uuid4()
    review = create_transaction(client, customer_id)
    assert review.json()["data"]["case"] is not None

    fake_ai.result = AIScoringResult(
        risk_score="0.75",
        fraud_type=FraudType.PARA_AKLAMA,
        decision=TransactionDecision.BLOK,
        risk_level=RiskLevel.YUKSEK,
        model_version="golden-v1",
    )
    blocked = create_transaction(client, customer_id)
    assert blocked.json()["data"]["case"] is not None
    assert blocked.json()["data"]["transaction"]["temporary_blocked"] is True


def test_critical_score_blocks_temporarily_and_sets_15_minute_sla(client, fake_ai):
    fake_ai.result = AIScoringResult(
        risk_score="0.91",
        fraud_type=FraudType.CALINTI_KART,
        decision=TransactionDecision.INCELEME,
        risk_level=RiskLevel.KRITIK,
        model_version="golden-v1",
    )
    response = create_transaction(client, uuid.uuid4())
    data = response.json()["data"]
    assert data["transaction"]["temporary_blocked"] is True
    assert 895 <= data["case"]["sla_remaining_seconds"] <= 900
    assert data["case"]["sla_exceeded"] is False


def test_customer_lists_only_own_transactions_and_idor_is_forbidden(client):
    owner = uuid.uuid4()
    stranger = uuid.uuid4()
    own = create_transaction(client, owner).json()["data"]["transaction"]
    create_transaction(client, stranger)

    listing = client.get("/transactions/me", headers=auth(owner, "CUSTOMER"))
    ids = [item["transaction"]["id"] for item in listing.json()["data"]["items"]]
    assert ids == [own["id"]]

    denied = client.get(
        f"/transactions/{own['id']}", headers=auth(stranger, "CUSTOMER")
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"


def test_analyst_sees_only_assigned_cases(client, fake_ai):
    analyst = uuid.uuid4()
    other = uuid.uuid4()
    fake_ai.result = AIScoringResult(
        risk_score="0.8",
        fraud_type=FraudType.SUPHELI_DAVRANIS,
        decision=TransactionDecision.INCELEME,
        risk_level=RiskLevel.YUKSEK,
        assigned_analyst_id=analyst,
    )
    assigned = create_transaction(client, uuid.uuid4()).json()["data"]
    fake_ai.result = fake_ai.result.model_copy(update={"assigned_analyst_id": other})
    create_transaction(client, uuid.uuid4())

    response = client.get("/cases/assigned-to-me", headers=auth(analyst, "ANALYST"))
    items = response.json()["data"]["items"]
    assert [item["id"] for item in items] == [assigned["case"]["id"]]
    view = client.get(
        f"/transactions/{assigned['transaction']['id']}",
        headers=auth(analyst, "ANALYST"),
    )
    assert view.status_code == 200


def test_supervisor_can_assign_fallback_case(client, fake_ai):
    fake_ai.unavailable = True
    case_id = create_transaction(client, uuid.uuid4()).json()["data"]["case"]["id"]
    analyst = uuid.uuid4()
    supervisor = uuid.uuid4()
    response = client.post(
        f"/cases/{case_id}/assign",
        json={"analyst_id": str(analyst)},
        headers=auth(supervisor, "SUPERVISOR"),
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ATANDI"
    assert response.json()["data"]["assigned_analyst_id"] == str(analyst)
    assert response.json()["data"]["history"][-1]["to_status"] == "ATANDI"


def test_valid_state_transitions_and_history_are_recorded(client, fake_ai, db):
    customer = uuid.uuid4()
    analyst = uuid.uuid4()
    fake_ai.result = fake_ai.result.model_copy(update={"assigned_analyst_id": analyst})
    case_id = create_transaction(client, customer).json()["data"]["case"]["id"]

    assert client.post(f"/cases/{case_id}/start", headers=auth(analyst, "ANALYST")).json()["data"]["status"] == "INCELENIYOR"
    verify = client.post(
        f"/cases/{case_id}/request-verification", headers=auth(analyst, "ANALYST")
    )
    assert verify.json()["data"]["status"] == "MUSTERI_DOGRULAMA"
    customer_response = client.post(
        f"/cases/{case_id}/customer-response",
        json={"response": "BEN_YAPMADIM"},
        headers=auth(customer, "CUSTOMER"),
    )
    assert customer_response.json()["data"]["status"] == "INCELENIYOR"
    assert customer_response.json()["data"]["customer_response"] == "BEN_YAPMADIM"
    decision = client.post(
        f"/cases/{case_id}/decision",
        json={"decision": "BLOKLANDI", "note": "Müşteri işlemi reddetti"},
        headers=auth(analyst, "ANALYST"),
    )
    assert decision.status_code == 200
    data = decision.json()["data"]
    assert data["status"] == "BLOKLANDI"
    assert data["decided_at"] is not None
    assert data["sla_remaining_seconds"] is None
    statuses = db.scalars(
        select(CaseHistory.to_status)
        .where(CaseHistory.case_id == uuid.UUID(case_id))
        .order_by(CaseHistory.created_at)
    ).all()
    assert statuses == [
        CaseStatus.YENI,
        CaseStatus.ATANDI,
        CaseStatus.INCELENIYOR,
        CaseStatus.MUSTERI_DOGRULAMA,
        CaseStatus.INCELENIYOR,
        CaseStatus.BLOKLANDI,
    ]


def test_invalid_transition_returns_422(client, fake_ai):
    fake_ai.unavailable = True
    case_id = create_transaction(client, uuid.uuid4()).json()["data"]["case"]["id"]
    response = client.post(
        f"/cases/{case_id}/start", headers=auth(uuid.uuid4(), "ANALYST")
    )
    assert response.status_code == 403  # not assigned is rejected before state disclosure

    analyst = uuid.uuid4()
    supervisor = uuid.uuid4()
    client.post(
        f"/cases/{case_id}/assign",
        json={"analyst_id": str(analyst)},
        headers=auth(supervisor, "SUPERVISOR"),
    )
    client.post(f"/cases/{case_id}/start", headers=auth(analyst, "ANALYST"))
    invalid = client.post(f"/cases/{case_id}/start", headers=auth(analyst, "ANALYST"))
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_CASE_TRANSITION"


def test_block_decision_requires_note(client, fake_ai):
    analyst = uuid.uuid4()
    fake_ai.result = fake_ai.result.model_copy(update={"assigned_analyst_id": analyst})
    case_id = create_transaction(client, uuid.uuid4()).json()["data"]["case"]["id"]
    client.post(f"/cases/{case_id}/start", headers=auth(analyst, "ANALYST"))
    response = client.post(
        f"/cases/{case_id}/decision",
        json={"decision": "BLOKLANDI"},
        headers=auth(analyst, "ANALYST"),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DECISION_NOTE_REQUIRED"


def test_customer_verification_requires_transaction_ownership(client, fake_ai):
    customer = uuid.uuid4()
    analyst = uuid.uuid4()
    fake_ai.result = fake_ai.result.model_copy(update={"assigned_analyst_id": analyst})
    case_id = create_transaction(client, customer).json()["data"]["case"]["id"]
    client.post(f"/cases/{case_id}/start", headers=auth(analyst, "ANALYST"))
    client.post(
        f"/cases/{case_id}/request-verification", headers=auth(analyst, "ANALYST")
    )
    response = client.post(
        f"/cases/{case_id}/customer-response",
        json={"response": "BEN_YAPTIM"},
        headers=auth(uuid.uuid4(), "CUSTOMER"),
    )
    assert response.status_code == 403


def test_supervisor_and_admin_can_list_cases_but_admin_cannot_decide(client):
    for role in ("SUPERVISOR", "ADMIN"):
        response = client.get("/cases", headers=auth(uuid.uuid4(), role))
        assert response.status_code == 200
    denied = client.post(
        f"/cases/{uuid.uuid4()}/decision",
        json={"decision": "ONAYLANDI"},
        headers=auth(uuid.uuid4(), "ADMIN"),
    )
    assert denied.status_code == 403


def test_case_list_supports_status_filter(client, fake_ai):
    fake_ai.unavailable = True
    create_transaction(client, uuid.uuid4())
    response = client.get(
        "/cases?status=YENI", headers=auth(uuid.uuid4(), "SUPERVISOR")
    )
    assert response.status_code == 200
    assert all(item["status"] == "YENI" for item in response.json()["data"]["items"])


def test_transition_service_supports_every_documented_edge():
    transitions = CaseTransitionService()
    now = datetime.now(timezone.utc)
    edges = {
        CaseStatus.YENI: (CaseStatus.ATANDI,),
        CaseStatus.ATANDI: (CaseStatus.INCELENIYOR,),
        CaseStatus.INCELENIYOR: (
            CaseStatus.MUSTERI_DOGRULAMA,
            CaseStatus.ONAYLANDI,
            CaseStatus.BLOKLANDI,
        ),
        CaseStatus.MUSTERI_DOGRULAMA: (CaseStatus.INCELENIYOR,),
        CaseStatus.ONAYLANDI: (CaseStatus.KAPANDI,),
        CaseStatus.BLOKLANDI: (CaseStatus.KAPANDI,),
    }
    for source, targets in edges.items():
        for target in targets:
            risk_case = RiskCase(
                id=uuid.uuid4(),
                transaction_id=uuid.uuid4(),
                status=source,
                sla_due_at=now,
            )
            history = transitions.transition(
                risk_case,
                target,
                actor_user_id=uuid.uuid4(),
                now=now,
            )
            assert risk_case.status is target
            assert history.from_status is source
            assert history.to_status is target


def test_missing_token_is_401_and_non_customer_create_is_403(client):
    assert client.post("/transactions", json=transaction_payload()).status_code == 401
    response = client.post(
        "/transactions",
        json=transaction_payload(),
        headers=auth(uuid.uuid4(), "ANALYST"),
    )
    assert response.status_code == 403

import uuid

from sqlalchemy import select

from app.models import AnalystProfile
from tests.conftest import analyst_payload, internal_headers, score_payload


def test_internal_key_is_required_and_wrong_key_is_forbidden(client):
    assert client.post("/score-and-assign", json=score_payload()).status_code == 401
    wrong = client.post(
        "/score-and-assign",
        json=score_payload(),
        headers={"X-Internal-Service-Key": "wrong"},
    )
    assert wrong.status_code == 403
    assert wrong.json()["error"]["code"] == "FORBIDDEN"


def test_analyst_sync_is_authenticated_normalized_and_idempotent(client, db):
    analyst_id = uuid.uuid4()
    payload = analyst_payload(
        analyst_id,
        specializations=[" calinti_kart ", "CALINTI_KART"],
        regions=[" tr ", "TR", "eu"],
    )
    first = client.post(
        "/internal/analysts/sync", json=payload, headers=internal_headers()
    )
    second = client.post(
        "/internal/analysts/sync",
        json={**payload, "accuracy_rate": "0.9500"},
        headers=internal_headers(),
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["specializations"] == ["CALINTI_KART"]
    assert first.json()["data"]["regions"] == ["TR", "EU"]
    profiles = db.scalars(select(AnalystProfile)).all()
    assert len(profiles) == 1
    assert str(profiles[0].accuracy_rate) == "0.9500"


def test_real_model_scores_and_assigns_matching_analyst(client, db):
    analyst_id = uuid.uuid4()
    sync = analyst_payload(
        analyst_id,
        specializations=[
            "CALINTI_KART",
            "HESAP_ELE_GECIRME",
            "PARA_AKLAMA",
            "SUPHELI_DAVRANIS",
        ],
    )
    client.post("/internal/analysts/sync", json=sync, headers=internal_headers())
    response = client.post(
        "/score-and-assign",
        json=score_payload(
            amount="180000.00",
            city="Moscow",
            occurred_at="2026-07-23T02:00:00Z",
            transaction_frequency_24h=14,
        ),
        headers={**internal_headers(), "X-Request-ID": "ai-score-live-test"},
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "ai-score-live-test"
    data = response.json()["data"]
    assert 0.70 <= data["risk_score"] <= 1.0
    assert data["assignment_status"] == "ASSIGNED"
    assert data["assigned_analyst_id"] == str(analyst_id)
    assert 0 <= data["assignment_score"] <= 1
    assert db.get(AnalystProfile, analyst_id).active_cases == 1


def test_low_risk_does_not_consume_analyst_capacity(client, db):
    analyst_id = uuid.uuid4()
    client.post(
        "/internal/analysts/sync",
        json=analyst_payload(analyst_id),
        headers=internal_headers(),
    )
    response = client.post(
        "/score-and-assign",
        json=score_payload(
            amount="250.00",
            transaction_type="FATURA",
            source_device="iPhone 15 Pro",
            city="Istanbul",
            occurred_at="2026-07-23T12:00:00Z",
            transaction_frequency_24h=2,
            is_new_device=False,
            home_city="Istanbul",
        ),
        headers=internal_headers(),
    )
    assert response.json()["data"]["decision"] == "ONAY"
    assert response.json()["data"]["assigned_analyst_id"] is None
    assert db.get(AnalystProfile, analyst_id).active_cases == 0

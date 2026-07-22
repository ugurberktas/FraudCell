import uuid
from decimal import Decimal
import json

import httpx
import pytest

from app.clients.ai_client import AIClient, AIServiceUnavailable
from app.schemas.transaction import TransactionCreate


def payload() -> TransactionCreate:
    return TransactionCreate.model_validate(
        {
            "amount": "48500.00",
            "transaction_type": "TRANSFER",
            "recipient": "Demo Alıcı",
            "source_device": "iPhone 15 Pro",
            "city": "Berlin",
            "occurred_at": "2026-07-23T10:00:00Z",
        }
    )


def test_ai_client_sends_internal_headers_and_parses_envelope():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "risk_score": 0.94,
                    "fraud_type": "CALINTI_KART",
                    "decision": "BLOK",
                    "risk_level": "KRITIK",
                    "model_version": "golden-ai-v1",
                    "assigned_analyst_id": None,
                },
                "error": None,
            },
        )

    client = AIClient(
        base_url="http://ai-service:8000",
        internal_service_key="internal-test-key",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )
    result = client.score_and_assign(
        transaction_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        transaction=payload(),
        request_id="request-123",
    )
    assert result.risk_score == Decimal("0.94")
    assert result.decision.value == "BLOK"
    request = captured["request"]
    assert request.url.path == "/api/v1/ai/score-and-assign"
    assert request.headers["X-Request-ID"] == "request-123"
    assert request.headers["X-Internal-Service-Key"] == "internal-test-key"
    assert captured["payload"]["transaction_frequency_24h"] == 1
    assert captured["payload"]["is_new_device"] is False
    assert captured["payload"]["home_city"] is None


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("timeout", request=request)),
        lambda request: httpx.Response(503, json={"error": "unavailable"}),
        lambda request: httpx.Response(200, json={"risk_score": "invalid"}),
    ],
)
def test_ai_timeout_http_failure_and_invalid_payload_trigger_fallback(handler):
    client = AIClient(
        base_url="http://ai-service:8000",
        internal_service_key="internal-test-key",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(AIServiceUnavailable):
        client.score_and_assign(
            transaction_id=uuid.uuid4(),
            customer_id=uuid.uuid4(),
            transaction=payload(),
            request_id="request-fallback",
        )

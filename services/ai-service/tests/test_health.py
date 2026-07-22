"""Tests for GET /health with envelope structure."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_returns_200_envelope() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["error"] is None
    assert body["data"]["status"] == "healthy"
    assert body["data"]["service"] == "ai-service"
    assert body["data"]["version"] == "0.1.0"

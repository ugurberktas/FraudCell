"""Tests for GET /ready with envelope structure."""
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_ready_db_connected() -> None:
    with patch("app.main.check_db_connection", return_value=True):
        response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["error"] is None
    assert body["data"]["status"] == "ready"
    assert body["data"]["service"] == "ai-service"
    assert body["data"]["database"] == "connected"


def test_ready_db_disconnected() -> None:
    with patch("app.main.check_db_connection", return_value=False):
        response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert body["error"]["message"] == "Database connection disconnected"
    assert body["error"]["details"]["database"] == "disconnected"

"""Tests for GET /ready — database connectivity is mocked."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ready_db_connected() -> None:
    """When check_db_connection returns True, /ready should return 200."""
    with patch("app.main.check_db_connection", return_value=True):
        response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["service"] == "identity-service"
    assert body["database"] == "connected"


def test_ready_db_disconnected() -> None:
    """When check_db_connection returns False, /ready should return 503."""
    with patch("app.main.check_db_connection", return_value=False):
        response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["service"] == "identity-service"
    assert body["database"] == "disconnected"

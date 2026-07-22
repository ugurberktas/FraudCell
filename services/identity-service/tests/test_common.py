"""Tests for common error handling, validation errors, internal error masking, and X-Request-ID middleware."""
import uuid
from pydantic import BaseModel
from fastapi.testclient import TestClient
from app.main import app

# Pass raise_server_exceptions=False so TestClient returns HTTP 500 instead of re-raising in test runner
client = TestClient(app, raise_server_exceptions=False)


class DummyPayload(BaseModel):
    number: int


@app.post("/test-validation-endpoint")
def dummy_validation_endpoint(payload: DummyPayload):
    return {"number": payload.number}


@app.get("/test-internal-error-endpoint")
def dummy_internal_error_endpoint():
    raise RuntimeError("Sensitive DB password leaked: postgres://user:secret@db:5432/db")


def test_not_found_returns_404_envelope() -> None:
    response = client.get("/nonexistent-endpoint")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert "X-Request-ID" in response.headers


def test_validation_error_returns_422_envelope() -> None:
    response = client.post("/test-validation-endpoint", json={"number": "invalid_integer"})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "X-Request-ID" in response.headers


def test_unhandled_exception_masks_internal_details() -> None:
    response = client.get("/test-internal-error-endpoint")
    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "An internal server error occurred."
    assert "postgres" not in response.text
    assert "secret" not in response.text
    assert "X-Request-ID" in response.headers


def test_request_id_preserved() -> None:
    custom_id = "test-custom-request-id-1234"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id


def test_request_id_auto_generated() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    req_id = response.headers.get("X-Request-ID")
    assert req_id is not None
    parsed_uuid = uuid.UUID(req_id, version=4)
    assert str(parsed_uuid) == req_id

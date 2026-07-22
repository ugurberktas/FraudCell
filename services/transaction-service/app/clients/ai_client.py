"""Synchronous HTTP client for the AI scoring boundary."""
from __future__ import annotations

import logging
import uuid

import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.ai import AIScoringResult
from app.schemas.transaction import TransactionCreate


logger = logging.getLogger(__name__)


class AIServiceUnavailable(Exception):
    """The AI response could not safely be used."""


class AIClient:
    def __init__(
        self,
        base_url: str | None = None,
        internal_service_key: str | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.ai_service_url).rstrip("/")
        self.internal_service_key = (
            settings.internal_service_key
            if internal_service_key is None
            else internal_service_key
        )
        self.timeout_seconds = timeout_seconds or settings.ai_timeout_seconds
        self.transport = transport

    def score_and_assign(
        self,
        *,
        transaction_id: uuid.UUID,
        customer_id: uuid.UUID,
        transaction: TransactionCreate,
        request_id: str,
    ) -> AIScoringResult:
        payload = {
            "transaction_id": str(transaction_id),
            "customer_id": str(customer_id),
            "amount": str(transaction.amount),
            "transaction_type": transaction.transaction_type.value,
            "recipient": transaction.recipient,
            "source_device": transaction.source_device,
            "city": transaction.city,
            "occurred_at": transaction.occurred_at.isoformat(),
            "transaction_frequency_24h": transaction.transaction_frequency_24h,
            "is_new_device": transaction.is_new_device,
            "home_city": transaction.home_city,
        }
        headers = {
            "X-Request-ID": request_id,
            "X-Internal-Service-Key": self.internal_service_key,
        }
        try:
            with httpx.Client(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = client.post(
                    f"{self.base_url}/api/v1/ai/score-and-assign",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                body = response.json()
            data = body.get("data") if isinstance(body, dict) and "data" in body else body
            if not isinstance(data, dict):
                raise ValueError("AI response payload is not an object")
            return AIScoringResult.model_validate(data)
        except (httpx.HTTPError, ValidationError, ValueError, TypeError) as exc:
            logger.warning(
                "AI scoring unavailable for request %s (%s)",
                request_id,
                type(exc).__name__,
            )
            raise AIServiceUnavailable("AI scoring is unavailable") from exc


def get_ai_client() -> AIClient:
    return AIClient()

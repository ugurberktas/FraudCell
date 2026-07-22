"""Constant-time authentication for internal service endpoints."""
import secrets

from fastapi import Header

from app.common.exceptions import AppException
from app.core.config import settings


def require_internal_service_key(
    x_internal_service_key: str | None = Header(default=None, alias="X-Internal-Service-Key"),
) -> None:
    if x_internal_service_key is None:
        raise AppException(
            "INTERNAL_AUTH_REQUIRED", "Internal service authentication is required", 401
        )
    configured_key = settings.internal_service_key
    if not configured_key or not secrets.compare_digest(
        x_internal_service_key, configured_key
    ):
        raise AppException("FORBIDDEN", "Access is forbidden", 403)

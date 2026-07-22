"""Custom domain exceptions."""
from typing import Any, Optional


class AppException(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.headers = headers or {}
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", details: Optional[dict] = None) -> None:
        super().__init__(code="RESOURCE_NOT_FOUND", message=message, status_code=404, details=details)


class ServiceUnavailableException(AppException):
    def __init__(self, message: str = "Service unavailable", details: Optional[dict] = None) -> None:
        super().__init__(code="SERVICE_UNAVAILABLE", message=message, status_code=503, details=details)

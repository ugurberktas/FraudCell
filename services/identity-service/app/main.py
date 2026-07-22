"""identity-service application entry point."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.encoders import jsonable_encoder

from app.api.routes.auth import router as auth_router
from app.api.routes.audit import router as audit_router
from app.api.routes.customers import router as customers_router
from app.common.exceptions import AppException
from app.common.middleware import RequestIDMiddleware
from app.common.responses import error_response, success_response
from app.core.config import settings
from app.db.session import check_db_connection

app = FastAPI(title=settings.service_name, version=settings.version)

app.add_middleware(RequestIDMiddleware)
app.include_router(customers_router)
app.include_router(auth_router)
app.include_router(audit_router)


def get_request_id_headers(request: Request) -> dict[str, str]:
    req_id = getattr(request.state, "request_id", None)
    return {"X-Request-ID": req_id} if req_id else {}


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    headers = get_request_id_headers(request)
    headers.update(exc.headers)
    return error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    safe_errors = [
        {key: value for key, value in error.items() if key not in {"input", "ctx"}}
        for error in exc.errors()
    ]
    return error_response(
        code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=422,
        details={"errors": jsonable_encoder(safe_errors)},
        headers=get_request_id_headers(request),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code_map = {
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "RESOURCE_NOT_FOUND",
        409: "CONFLICT",
        429: "RATE_LIMITED",
        503: "SERVICE_UNAVAILABLE",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    message = str(exc.detail) if exc.detail else "An HTTP error occurred."
    return error_response(
        code=code,
        message=message,
        status_code=exc.status_code,
        headers=get_request_id_headers(request),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return error_response(
        code="INTERNAL_ERROR",
        message="An internal server error occurred.",
        status_code=500,
        headers=get_request_id_headers(request),
    )


@app.get("/health")
def health_check():
    return success_response(
        data={
            "status": "healthy",
            "service": settings.service_name,
            "version": settings.version,
        }
    )


@app.get("/ready")
def readiness_check(request: Request):
    is_connected = check_db_connection()
    if is_connected:
        return success_response(
            data={
                "status": "ready",
                "service": settings.service_name,
                "database": "connected",
            }
        )
    return error_response(
        code="SERVICE_UNAVAILABLE",
        message="Database connection disconnected",
        status_code=503,
        details={
            "service": settings.service_name,
            "database": "disconnected",
        },
        headers=get_request_id_headers(request),
    )

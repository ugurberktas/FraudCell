from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db.session import check_db_connection

app = FastAPI(
    title=settings.service_name,
    version=settings.version,
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Return service liveness status. Independent of database availability."""
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.version,
    }


@app.get("/ready", tags=["health"])
async def readiness_check():
    """Return service readiness status by verifying database connectivity."""
    connected = check_db_connection()
    if connected:
        return {
            "status": "ready",
            "service": settings.service_name,
            "database": "connected",
        }
    return JSONResponse(
        status_code=503,
        content={
            "status": "not_ready",
            "service": settings.service_name,
            "database": "disconnected",
        },
    )

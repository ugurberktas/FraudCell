"""Database session management for gamification-service."""
from __future__ import annotations

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings

logger = logging.getLogger(__name__)

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def check_db_connection() -> bool:
    """Execute SELECT 1 against the configured database.

    Returns True if the database is reachable, False otherwise.
    Designed to be easily mockable in unit tests.
    """
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, Exception) as exc:  # noqa: BLE001
        logger.warning("Database connectivity check failed: %s", exc)
        return False


def get_db():
    with Session(_get_engine()) as session:
        try:
            yield session
        finally:
            session.rollback()

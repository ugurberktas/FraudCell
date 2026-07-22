"""FastAPI database dependencies."""
from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import _get_engine


def get_db() -> Generator[Session, None, None]:
    """Provide one SQLAlchemy session per request.

    Services own their transaction boundaries; any still-open transaction is
    rolled back when the request scope ends.
    """
    with Session(_get_engine()) as session:
        try:
            yield session
        finally:
            session.rollback()

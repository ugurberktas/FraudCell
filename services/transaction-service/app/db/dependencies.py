"""FastAPI database dependencies."""
from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import _get_engine


def get_db() -> Generator[Session, None, None]:
    with Session(_get_engine()) as session:
        try:
            yield session
        finally:
            session.rollback()

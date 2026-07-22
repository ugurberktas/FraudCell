"""Refresh-token persistence with row locking for rotation."""
from datetime import datetime
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(token)
        self.session.flush()
        return token

    def get_by_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        statement = (
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .limit(1)
            .with_for_update()
        )
        return self.session.scalar(statement)

    def revoke_all_active(self, user_id: uuid.UUID, revoked_at: datetime) -> None:
        self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )

"""Add OTP purposes and enforce unique refresh token hashes.

Revision ID: 003_auth_token_foundation
Revises: 002_require_user_names
Create Date: 2026-07-23 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "003_auth_token_foundation"
down_revision: Union[str, None] = "002_require_user_names"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

otp_purpose_enum = postgresql.ENUM(
    "REGISTER", "LOGIN", name="otp_purpose_enum"
)


def upgrade() -> None:
    otp_purpose_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "otp_challenges",
        sa.Column(
            "purpose",
            postgresql.ENUM(
                "REGISTER", "LOGIN", name="otp_purpose_enum", create_type=False
            ),
            nullable=False,
            server_default="REGISTER",
        ),
    )

    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.create_index(
        "ix_refresh_tokens_token_hash",
        "refresh_tokens",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.create_index(
        "ix_refresh_tokens_token_hash",
        "refresh_tokens",
        ["token_hash"],
        unique=False,
    )
    op.drop_column("otp_challenges", "purpose")
    otp_purpose_enum.drop(op.get_bind(), checkfirst=True)

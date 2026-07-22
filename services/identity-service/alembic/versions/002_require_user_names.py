"""Require first and last names for identity users.

Revision ID: 002_require_user_names
Revises: 001_initial_identity_schema
Create Date: 2026-07-23 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002_require_user_names"
down_revision: Union[str, None] = "001_initial_identity_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "first_name",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.alter_column(
        "users",
        "last_name",
        existing_type=sa.String(length=100),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "last_name",
        existing_type=sa.String(length=100),
        nullable=True,
    )
    op.alter_column(
        "users",
        "first_name",
        existing_type=sa.String(length=100),
        nullable=True,
    )

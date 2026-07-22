"""Create analyst profiles for deterministic assignment.

Revision ID: 001_initial_ai_schema
Revises:
Create Date: 2026-07-23 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_ai_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analyst_profiles",
        sa.Column("analyst_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("specializations", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("regions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("active_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_active_cases", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("accuracy_rate", sa.Numeric(5, 4), nullable=False, server_default="0.8000"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "active_cases >= 0", name="ck_analyst_profiles_active_cases"
        ),
        sa.CheckConstraint(
            "max_active_cases > 0", name="ck_analyst_profiles_max_active_cases"
        ),
        sa.CheckConstraint(
            "accuracy_rate >= 0 AND accuracy_rate <= 1",
            name="ck_analyst_profiles_accuracy_rate",
        ),
    )


def downgrade() -> None:
    op.drop_table("analyst_profiles")

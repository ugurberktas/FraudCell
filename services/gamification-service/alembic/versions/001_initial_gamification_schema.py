"""initial gamification schema

Revision ID: 001_initial_gamification_schema
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial_gamification_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processed_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_processed_events_event_id", "processed_events", ["event_id"])
    op.create_table(
        "analyst_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analyst_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("total_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolved_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("level", sa.String(20), nullable=False, server_default="BRONZ"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_analyst_profiles_analyst_id", "analyst_profiles", ["analyst_id"])
    op.create_table(
        "score_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analyst_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analyst_profiles.analyst_id", ondelete="CASCADE"), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("event_id", "reason", name="uq_score_ledger_event_reason"),
    )
    op.create_index("ix_score_ledger_event_id", "score_ledger", ["event_id"])
    op.create_index("ix_score_ledger_analyst_id", "score_ledger", ["analyst_id"])
    op.create_index("ix_score_ledger_occurred_at", "score_ledger", ["occurred_at"])
    op.create_table(
        "badges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analyst_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analyst_profiles.analyst_id", ondelete="CASCADE"), nullable=False),
        sa.Column("badge_code", sa.String(50), nullable=False),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.UniqueConstraint("analyst_id", "badge_code", name="uq_badges_analyst_code"),
    )
    op.create_index("ix_badges_analyst_id", "badges", ["analyst_id"])


def downgrade() -> None:
    op.drop_index("ix_badges_analyst_id", table_name="badges")
    op.drop_table("badges")
    op.drop_index("ix_score_ledger_occurred_at", table_name="score_ledger")
    op.drop_index("ix_score_ledger_analyst_id", table_name="score_ledger")
    op.drop_index("ix_score_ledger_event_id", table_name="score_ledger")
    op.drop_table("score_ledger")
    op.drop_index("ix_analyst_profiles_analyst_id", table_name="analyst_profiles")
    op.drop_table("analyst_profiles")
    op.drop_index("ix_processed_events_event_id", table_name="processed_events")
    op.drop_table("processed_events")

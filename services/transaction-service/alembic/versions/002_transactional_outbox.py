"""add transactional outbox

Revision ID: 002_transactional_outbox
Revises: 001_initial_transaction_schema
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_transactional_outbox"
down_revision = "001_initial_transaction_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("routing_key", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.UniqueConstraint("event_id", name="uq_outbox_events_event_id"),
    )
    op.create_index("ix_outbox_events_event_id", "outbox_events", ["event_id"])
    op.create_index("ix_outbox_events_created_at", "outbox_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_outbox_events_created_at", table_name="outbox_events")
    op.drop_index("ix_outbox_events_event_id", table_name="outbox_events")
    op.drop_table("outbox_events")

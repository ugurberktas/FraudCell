"""add customer feedback

Revision ID: 003_customer_feedback
Revises: 002_transactional_outbox
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_customer_feedback"
down_revision = "002_transactional_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("risk_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_customer_feedback_rating"),
        sa.UniqueConstraint("case_id", name="uq_customer_feedback_case_id"),
    )
    op.create_index("ix_customer_feedback_case_id", "customer_feedback", ["case_id"])
    op.create_index("ix_customer_feedback_customer_id", "customer_feedback", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_customer_feedback_customer_id", table_name="customer_feedback")
    op.drop_index("ix_customer_feedback_case_id", table_name="customer_feedback")
    op.drop_table("customer_feedback")

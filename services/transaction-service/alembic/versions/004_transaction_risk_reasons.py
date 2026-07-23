"""persist AI risk reasons on transactions

Revision ID: 004_transaction_risk_reasons
Revises: 003_customer_feedback
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "004_transaction_risk_reasons"
down_revision = "003_customer_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column(
            "risk_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("transactions", "risk_reasons", server_default=None)


def downgrade() -> None:
    op.drop_column("transactions", "risk_reasons")

"""Initial transaction golden-path schema.

Revision ID: 001_initial_transaction_schema
Revises:
Create Date: 2026-07-23 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_transaction_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

transaction_type_enum = postgresql.ENUM(
    "ODEME", "TRANSFER", "FATURA", "CEKIM", name="transaction_type_enum"
)
fraud_type_enum = postgresql.ENUM(
    "CALINTI_KART",
    "HESAP_ELE_GECIRME",
    "PARA_AKLAMA",
    "SUPHELI_DAVRANIS",
    "TEMIZ",
    name="fraud_type_enum",
)
transaction_decision_enum = postgresql.ENUM(
    "ONAY", "INCELEME", "BLOK", name="transaction_decision_enum"
)
risk_level_enum = postgresql.ENUM(
    "DUSUK", "ORTA", "YUKSEK", "KRITIK", "BELIRSIZ", name="risk_level_enum"
)
ai_status_enum = postgresql.ENUM("SCORED", "UNAVAILABLE", name="ai_status_enum")
case_status_enum = postgresql.ENUM(
    "YENI",
    "ATANDI",
    "INCELENIYOR",
    "MUSTERI_DOGRULAMA",
    "ONAYLANDI",
    "BLOKLANDI",
    "KAPANDI",
    name="case_status_enum",
)
customer_response_enum = postgresql.ENUM(
    "BEN_YAPTIM", "BEN_YAPMADIM", "YANIT_YOK", name="customer_response_enum"
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (
        transaction_type_enum,
        fraud_type_enum,
        transaction_decision_enum,
        risk_level_enum,
        ai_status_enum,
        case_status_enum,
        customer_response_enum,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "transaction_number_sequences",
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("last_value", sa.Integer(), nullable=False),
    )
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_number", sa.String(20), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "transaction_type",
            postgresql.ENUM(name="transaction_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("source_device", sa.String(255), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_score", sa.Numeric(6, 5), nullable=True),
        sa.Column(
            "fraud_type",
            postgresql.ENUM(name="fraud_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "decision",
            postgresql.ENUM(name="transaction_decision_enum", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "risk_level",
            postgresql.ENUM(name="risk_level_enum", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "ai_status",
            postgresql.ENUM(name="ai_status_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("model_version", sa.String(100), nullable=True),
        sa.Column("temporary_blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "transaction_number", name="uq_transactions_transaction_number"
        ),
    )
    op.create_index("ix_transactions_transaction_number", "transactions", ["transaction_number"])
    op.create_index("ix_transactions_customer_id", "transactions", ["customer_id"])

    op.create_table(
        "risk_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="case_status_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("assigned_analyst_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column(
            "customer_response",
            postgresql.ENUM(name="customer_response_enum", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_risk_cases_transaction_id", "risk_cases", ["transaction_id"], unique=True)
    op.create_index("ix_risk_cases_assigned_analyst_id", "risk_cases", ["assigned_analyst_id"])

    op.create_table(
        "case_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("risk_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_status",
            postgresql.ENUM(name="case_status_enum", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            postgresql.ENUM(name="case_status_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_case_history_case_id", "case_history", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_case_history_case_id", table_name="case_history")
    op.drop_table("case_history")
    op.drop_index("ix_risk_cases_assigned_analyst_id", table_name="risk_cases")
    op.drop_index("ix_risk_cases_transaction_id", table_name="risk_cases")
    op.drop_table("risk_cases")
    op.drop_index("ix_transactions_customer_id", table_name="transactions")
    op.drop_index("ix_transactions_transaction_number", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("transaction_number_sequences")

    bind = op.get_bind()
    for enum_type in reversed(
        (
            transaction_type_enum,
            fraud_type_enum,
            transaction_decision_enum,
            risk_level_enum,
            ai_status_enum,
            case_status_enum,
            customer_response_enum,
        )
    ):
        enum_type.drop(bind, checkfirst=True)

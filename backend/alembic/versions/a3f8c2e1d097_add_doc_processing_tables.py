"""add_doc_processing_tables

Revision ID: a3f8c2e1d097
Revises: cef3d148da25
Create Date: 2026-03-31 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f8c2e1d097"
down_revision: Union[str, Sequence[str], None] = "cef3d148da25"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. batch_runs — no FK dependencies
    op.create_table(
        "batch_runs",
        sa.Column("batch_id", sa.String(64), primary_key=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_files", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_records", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="In Progress"),
    )
    op.create_index("ix_batch_runs_status", "batch_runs", ["status"])

    # 2. run_records — FK → batch_runs.batch_id
    op.create_table(
        "run_records",
        sa.Column("record_id", sa.String(64), primary_key=True),
        sa.Column(
            "batch_id", sa.String(64),
            sa.ForeignKey("batch_runs.batch_id"),
            nullable=False,
        ),
        sa.Column("source_filename", sa.String(512), nullable=False),
        sa.Column("work_path", sa.String(1024), nullable=False),
        sa.Column("guid_filename", sa.String(576), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="Pending"),
    )
    op.create_index("ix_run_records_batch_id", "run_records", ["batch_id"])
    op.create_index("ix_run_records_status", "run_records", ["status"])

    # 3. payment_records — FK → run_records.record_id
    op.create_table(
        "payment_records",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "run_record_id", sa.String(64),
            sa.ForeignKey("run_records.record_id"),
            nullable=False,
        ),
        sa.Column("batch_id", sa.String(64), nullable=False),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("customer_name", sa.String(512), nullable=True),
        sa.Column("account_number", sa.String(128), nullable=True),
        sa.Column("payee", sa.String(512), nullable=True),
        sa.Column("payment_id", sa.String(128), nullable=True),
        sa.Column("payment_method", sa.String(64), nullable=True),
        sa.Column("payment_date", sa.String(32), nullable=True),
        sa.Column("invoice_number", sa.String(128), nullable=True),
        sa.Column("reference_doc_number", sa.String(128), nullable=True),
        sa.Column("amount_paid", sa.Float, nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("deductions", sa.Float, nullable=True),
        sa.Column("deduction_type", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("validation_status", sa.String(32), nullable=False),
        sa.Column("confidence_scores", sa.Text, nullable=False),
        sa.Column("overall_confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("llm_provider", sa.String(64), nullable=False),
        sa.Column("llm_model", sa.String(128), nullable=False),
        sa.Column("source_filename", sa.String(512), nullable=False),
        sa.Column("doc_type", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payment_records_batch_id", "payment_records", ["batch_id"])
    op.create_index("ix_payment_records_validation_status", "payment_records", ["validation_status"])
    op.create_index("ix_payment_records_run_record_id", "payment_records", ["run_record_id"])


def downgrade() -> None:
    op.drop_table("payment_records")
    op.drop_table("run_records")
    op.drop_table("batch_runs")

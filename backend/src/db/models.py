"""SQLAlchemy ORM models — code-first approach.

These map directly to database tables. Alembic (or Base.metadata.create_all)
generates the DDL. Pydantic schemas in src/schemas/ handle API serialisation;
these models handle persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class AppSettingModel(Base):
    """Key-value application settings stored in the database."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")


class DocumentModel(Base):
    """Persisted document flowing through the reconciliation pipeline."""

    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_email: Mapped[str] = mapped_column(String(256), nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(256))
    amount: Mapped[str | None] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(8), default="ZAR")
    bank_reference_id: Mapped[str | None] = mapped_column(String(128))
    payment_date: Mapped[str | None] = mapped_column(String(32))
    attachment_mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="Ingested")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_documents_state", "state"),
    )


class BankTransactionModel(Base):
    """Bank statement line item."""

    __tablename__ = "bank_transactions"

    transaction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_name: Mapped[str] = mapped_column(String(256), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    date: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(128))

    __table_args__ = (
        Index("ix_bank_transactions_reference_id", "reference_id"),
    )


class MatchResultModel(Base):
    """Persisted match result from the Auditor Agent."""

    __tablename__ = "match_results"

    match_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), nullable=False)
    bank_transaction_id: Mapped[str | None] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_delta: Mapped[float] = mapped_column(Float, nullable=False)
    name_similarity: Mapped[float | None] = mapped_column(Float)
    bank_reference_id_match: Mapped[bool] = mapped_column(default=False)
    temporal_delta_days: Mapped[int | None] = mapped_column()
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_match_results_document_id", "document_id"),
    )


class AuditLogModel(Base):
    """Append-only audit reasoning log entry. No PII. Immutable once written."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    state_from: Mapped[str] = mapped_column(String(32), nullable=False)
    state_to: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_scores: Mapped[str | None] = mapped_column(Text)  # JSON-serialised dict

    __table_args__ = (
        Index("ix_audit_log_agent", "agent"),
        Index("ix_audit_log_timestamp", "timestamp"),
    )


# ── Doc Processing Pipeline Models ────────────────────────────────────────


class BatchRunModel(Base):
    """One row per UI-triggered pipeline batch run."""

    __tablename__ = "batch_runs"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="In Progress")

    __table_args__ = (
        Index("ix_batch_runs_status", "status"),
    )


class RunRecordModel(Base):
    """One row per file within a BatchRun."""

    __tablename__ = "run_records"

    record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    work_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    guid_filename: Mapped[str] = mapped_column(String(576), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")

    __table_args__ = (
        Index("ix_run_records_batch_id", "batch_id"),
        Index("ix_run_records_status", "status"),
    )


class PaymentRecordModel(Base):
    """One row per extracted payment amount. Many per run_record / batch_run."""

    __tablename__ = "payment_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_record_id: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 14 extracted payment fields (all nullable)
    customer_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payee: Mapped[str | None] = mapped_column(String(512), nullable=True)
    payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reference_doc_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount_paid: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    deductions: Mapped[float | None] = mapped_column(Float, nullable=True)
    deduction_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Validation & metadata
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_scores: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    overall_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    llm_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_payment_records_batch_id", "batch_id"),
        Index("ix_payment_records_validation_status", "validation_status"),
        Index("ix_payment_records_run_record_id", "run_record_id"),
    )

"""SQLAlchemy ORM models — code-first approach.

These map directly to database tables. Alembic (or Base.metadata.create_all)
generates the DDL. Pydantic schemas in src/schemas/ handle API serialisation;
these models handle persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


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

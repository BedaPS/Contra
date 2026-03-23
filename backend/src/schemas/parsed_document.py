"""Pydantic schemas for parsed documents and OCR output."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DocumentState(str, enum.Enum):
    INGESTED = "Ingested"
    PARSED = "Parsed"
    PII_REDACTED = "PII_Redacted"
    MATCHED = "Matched"
    FINALIZED = "Finalized"
    ERROR_QUEUE = "Error_Queue"
    INCOMPLETE_DATA = "Incomplete_Data"
    EXCEPTION_REVIEW = "Exception_Review"
    NEEDS_REVIEW = "Needs_Review"
    HUMAN_REVIEW = "Human_Review"
    AUDIT_TRAIL_FAILURE = "Audit_Trail_Failure"


class FieldConfidence(BaseModel):
    """A single extracted field with its OCR confidence score."""

    value: Optional[str] = None
    confidence_score: float = Field(
        ge=0.0, le=1.0,
        description="OCR confidence for this field (0.0–1.0).",
    )


class ParsedDocument(BaseModel):
    """Output of the Vision (OCR) Agent — strict JSON, no prose."""

    document_id: str
    source_email: str = Field(
        description="Sender email address (masked after PII redaction).",
    )
    account_name: FieldConfidence
    amount: FieldConfidence
    currency: FieldConfidence = FieldConfidence(value="ZAR", confidence_score=1.0)
    bank_reference_id: Optional[FieldConfidence] = None
    payment_date: FieldConfidence
    attachment_mime_type: str
    state: DocumentState = DocumentState.INGESTED
    created_at: datetime = Field(default_factory=datetime.utcnow)
    raw_text: Optional[str] = Field(
        default=None,
        description="Raw OCR text. Cleared after PII redaction.",
    )

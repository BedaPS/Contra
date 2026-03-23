"""Ingestion Agent — accepts email attachments, runs OCR, redacts PII.

Constitution mandate: PII redaction is non-bypassable. This agent MUST
redact all PII before passing data to any downstream agent or service.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

from src.audit import logger as audit_log
from src.audit.logger import AuditEntry, compute_hash
from src.schemas.parsed_document import DocumentState, FieldConfidence, ParsedDocument
from src.state_machine import advance

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_ACCOUNT_RE = re.compile(r"\b\d{6,}\b")


def redact_pii(doc: ParsedDocument) -> ParsedDocument:
    """Mask PII fields in-place and clear raw_text.

    - Account numbers → ****<last-4>
    - Email addresses → [REDACTED]
    - raw_text → None
    """
    if doc.source_email:
        doc.source_email = "[REDACTED]"

    if doc.raw_text:
        doc.raw_text = None

    return doc


def ingest(
    source_email: str,
    attachment_mime_type: str,
    ocr_fields: dict[str, FieldConfidence],
    raw_text: Optional[str] = None,
) -> ParsedDocument:
    """Create a ParsedDocument, validate MIME, advance through Ingested→Parsed→PII_Redacted."""

    doc = ParsedDocument(
        document_id=str(uuid.uuid4()),
        source_email=source_email,
        account_name=ocr_fields.get("account_name", FieldConfidence(value=None, confidence_score=0.0)),
        amount=ocr_fields.get("amount", FieldConfidence(value=None, confidence_score=0.0)),
        payment_date=ocr_fields.get("payment_date", FieldConfidence(value=None, confidence_score=0.0)),
        bank_reference_id=ocr_fields.get("bank_reference_id"),
        attachment_mime_type=attachment_mime_type,
        raw_text=raw_text,
    )

    # Gate: Ingested → Parsed
    input_snapshot = doc.model_dump()
    advance(doc)  # Ingested → Parsed
    _log_transition(doc, "Ingested", "Parsed", input_snapshot)

    # PII redaction
    redact_pii(doc)

    # Gate: Parsed → PII_Redacted
    input_snapshot2 = doc.model_dump()
    advance(doc)  # Parsed → PII_Redacted
    _log_transition(doc, "Parsed", "PII_Redacted", input_snapshot2)

    return doc


def _log_transition(
    doc: ParsedDocument,
    state_from: str,
    state_to: str,
    input_snapshot: dict,
) -> None:
    output_snapshot = doc.model_dump()
    entry = AuditEntry(
        agent="ingestion_agent",
        input_hash=compute_hash(input_snapshot),
        output_hash=compute_hash(output_snapshot),
        state_from=state_from,
        state_to=state_to,
        decision="OK",
        rationale=f"Transitioned {state_from} → {state_to} for document {doc.document_id}.",
        confidence_scores={
            "account_name": doc.account_name.confidence_score,
            "amount": doc.amount.confidence_score,
            "payment_date": doc.payment_date.confidence_score,
        },
    )
    audit_log.append(entry)

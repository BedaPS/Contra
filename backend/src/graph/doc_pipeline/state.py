"""State for the document-processing LangGraph pipeline.

DocPipelineState is per-file — a new instance is created for each source file
processed by the DocPipeline graph. It is completely independent of ContraState
(the reconciliation pipeline). See research.md §Decision 9.
"""

from __future__ import annotations

from typing import Annotated, Any

from typing_extensions import TypedDict


def _replace(existing: Any, new: Any) -> Any:
    """Reducer that replaces the old value with the new value (last-write-wins)."""
    return new


class PaymentRecordDict(TypedDict, total=False):
    """Extracted payment record carried in-flight before DB write.

    All 14 extracted fields are nullable — the LLM may not find every field in
    every document. ``confidence_scores`` and ``validation_status`` are always
    set by the extractor / validator nodes respectively.
    """

    # 14 extracted fields
    customer_name: str | None
    account_number: str | None  # NEVER written to audit logs — only confidence score logged
    payee: str | None
    payment_id: str | None
    payment_method: str | None  # normalised: EFT|CASH|CHEQUE|DIRECT_DEPOSIT|CARD
    payment_date: str | None    # normalised: YYYY-MM-DD
    invoice_number: str | None
    reference_doc_number: str | None
    amount_paid: float | None   # normalised: float; critical field (threshold 0.90)
    currency: str | None        # normalised: ISO 4217
    deductions: float | None    # normalised: float
    deduction_type: str | None
    notes: str | None

    # Extraction metadata
    page_number: int | None         # 1-based page index where this record was found
    confidence_scores: dict[str, float]  # {field_name: 0.0-1.0}
    validation_status: str          # 'Valid'|'Review Required'|'Extraction Failed'


class DocPipelineState(TypedDict, total=False):
    """Shared state flowing through the document processing graph.

    All fields use ``_replace`` (last-write-wins). The state is created fresh
    for each file invocation — no accumulated history between files.
    """

    # ── Run context ──
    batch_id: Annotated[str, _replace]
    run_record_id: Annotated[str, _replace]

    # ── File paths ──
    source_file_path: Annotated[str, _replace]
    work_file_path: Annotated[str, _replace]
    guid_filename: Annotated[str, _replace]

    # ── Classifier output ──
    doc_type: Annotated[str | None, _replace]        # 'email'|'remittance'|'receipt'|'unknown'
    prompt_config: Annotated[dict | None, _replace]  # loaded YAML config dict

    # ── Extractor input ──
    page_images: Annotated[list[str], _replace]      # base64-encoded PNG per page

    # ── Extractor → Normaliser → Validator chain ──
    raw_records: Annotated[list[PaymentRecordDict], _replace]          # post-extraction
    normalised_records: Annotated[list[PaymentRecordDict], _replace]   # post-normalisation
    validated_records: Annotated[list[PaymentRecordDict], _replace]    # post-validation

    # ── Retry tracking ──
    extraction_attempts: Annotated[int, _replace]    # 0-based; max 3 per spec

    # ── Error tracking ──
    error: Annotated[str | None, _replace]
    error_type: Annotated[str | None, _replace]      # 'parse_error'|'rate_limit'|'all_null'

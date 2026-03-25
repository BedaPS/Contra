"""Enrichment Agent — augments parsed document data before matching.

Sits between OCR extraction and PII redaction in the pipeline.
Enriches extracted fields with additional data lookups, cross-references,
and derived values to improve downstream matching accuracy.

Constitution compliance:
- No PII leakage: enrichment works on extracted OCR fields only.
- All LLM calls go through llm_adapter.py.
- Audit trail entry written for every enrichment action.
"""

from __future__ import annotations

from src.adapters.llm_adapter import LLMAdapter


async def enrich_fields(
    llm: LLMAdapter,
    ocr_fields: dict,
    work_file_path: str | None = None,
) -> dict:
    """Enrich OCR-extracted fields with additional data.

    Stub — will be extended as enrichment sources are defined.
    Returns the enriched fields dict (may add or modify field entries).

    Args:
        llm: The LLM adapter for any reasoning calls.
        ocr_fields: Dict of field_name -> {"value": ..., "confidence_score": ...}.
        work_file_path: Path to the working copy of the document (for re-reading if needed).

    Returns:
        Updated ocr_fields dict with enriched data.
    """
    _ = llm, work_file_path  # Suppress unused warnings until wired
    # Pass-through for now — enrichment logic will be added per use case
    return ocr_fields

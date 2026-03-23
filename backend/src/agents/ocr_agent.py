"""Vision (OCR) Agent — extract structured fields from payment proof images/PDFs.

Constitution mandate:
- Every field MUST include a confidence_score.
- Fields below 0.85 → NEEDS_REVIEW, document blocked from matching.
- No inference of illegible characters. Ambiguous values → null.
- Output MUST be valid JSON (ParsedDocument schema). No prose.
"""

from __future__ import annotations

from src.adapters.llm_adapter import LLMAdapter
from src.schemas.parsed_document import FieldConfidence

# Confidence threshold — constitution §Vision Agent Protocol
CONFIDENCE_THRESHOLD = 0.85

SYSTEM_PROMPT = (
    "You are the Vision Agent of Contra. Extract payment proof fields from the "
    "provided document image/text. For every field, output a JSON object with "
    "'value' (string or null) and 'confidence_score' (float 0.0–1.0). "
    "If a character or digit is illegible, set value to null and confidence_score "
    "below 0.85. Do NOT guess. Output only valid JSON — no prose."
)


def needs_review(fields: dict[str, FieldConfidence]) -> list[str]:
    """Return field names whose confidence is below the constitution threshold."""
    return [
        name for name, field in fields.items()
        if field.confidence_score < CONFIDENCE_THRESHOLD
    ]


async def extract_fields(llm: LLMAdapter, document_text: str) -> dict[str, FieldConfidence]:
    """Call the LLM via the adapter to extract structured OCR fields.

    Stub — will be wired during the OCR feature implementation.
    Returns a placeholder dict for now.
    """
    _ = llm, document_text  # Suppress unused warnings until wired
    raise NotImplementedError(
        "Vision Agent OCR extraction not yet implemented. "
        "Wire LLMAdapter.complete() with the OCR prompt first."
    )

"""Five-state gate enforcement for document lifecycle.

States: Ingested → Parsed → PII_Redacted → Matched → Finalized
Each transition has a hard check. Bypassing a gate is a constitution violation.
"""

from __future__ import annotations

from src.schemas.parsed_document import DocumentState, ParsedDocument

_ALLOWED_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff", "image/webp"}

# Ordered happy-path transitions
_TRANSITIONS: dict[DocumentState, DocumentState] = {
    DocumentState.INGESTED: DocumentState.PARSED,
    DocumentState.PARSED: DocumentState.PII_REDACTED,
    DocumentState.PII_REDACTED: DocumentState.MATCHED,
    DocumentState.MATCHED: DocumentState.FINALIZED,
}

_PII_MARKERS = {"****", "[REDACTED]"}


class GateError(Exception):
    """Raised when a state-machine gate check fails."""

    def __init__(self, current_state: DocumentState, target_state: DocumentState, reason: str) -> None:
        self.current_state = current_state
        self.target_state = target_state
        self.reason = reason
        super().__init__(f"Gate {current_state.value}→{target_state.value} failed: {reason}")


def _check_ingested(doc: ParsedDocument) -> DocumentState | None:
    """Attachment must be PDF or image."""
    if doc.attachment_mime_type not in _ALLOWED_MIME_TYPES:
        return DocumentState.ERROR_QUEUE
    return None


def _check_parsed(doc: ParsedDocument) -> DocumentState | None:
    """Amount and account_name must be non-null and non-empty."""
    if not doc.amount.value or not doc.account_name.value:
        return DocumentState.INCOMPLETE_DATA
    return None


def _check_pii_redacted(doc: ParsedDocument) -> DocumentState | None:
    """All PII fields must be masked; raw_text must be cleared."""
    if doc.raw_text is not None:
        return DocumentState.ERROR_QUEUE
    # source_email should be redacted
    if doc.source_email and "@" in doc.source_email and not any(m in doc.source_email for m in _PII_MARKERS):
        return DocumentState.ERROR_QUEUE
    return None


_GATE_CHECKS: dict[DocumentState, object] = {
    DocumentState.INGESTED: _check_ingested,
    DocumentState.PARSED: _check_parsed,
    DocumentState.PII_REDACTED: _check_pii_redacted,
    # MATCHED and FINALIZED gates are enforced by the Auditor Agent and receipt dispatcher respectively.
}


def advance(doc: ParsedDocument) -> DocumentState:
    """Attempt to advance *doc* to its next state.

    Returns the new state on success.
    Raises GateError if the gate check fails or the transition is invalid.
    """
    next_state = _TRANSITIONS.get(doc.state)
    if next_state is None:
        raise GateError(doc.state, DocumentState.FINALIZED, "No further transitions from this state.")

    gate_fn = _GATE_CHECKS.get(doc.state)
    if gate_fn is not None:
        failure_route = gate_fn(doc)  # type: ignore[operator]
        if failure_route is not None:
            raise GateError(doc.state, next_state, f"Routed to {failure_route.value}")

    doc.state = next_state
    return next_state

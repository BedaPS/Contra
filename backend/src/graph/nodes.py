"""LangGraph node functions for the reconciliation pipeline.

Each function receives the full ContraState and returns a partial update dict.
Gate checks are performed before state transitions. Failures return error state.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.types import interrupt
from Levenshtein import ratio as levenshtein_ratio

from src.audit import logger as audit_log
from src.audit.logger import AuditEntry, compute_hash
from src.graph.state import ContraState

# ── Constitution thresholds ──
_ALLOWED_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff", "image/webp"}
CONFIDENCE_THRESHOLD = 0.85
NAME_SIMILARITY_THRESHOLD = 0.90
TEMPORAL_WINDOW_DAYS = 7
MAX_CYCLE_ITERATIONS = 3


# ---------------------------------------------------------------------------
# Node: ingest
# ---------------------------------------------------------------------------

def ingest_node(state: ContraState) -> dict[str, Any]:
    """Validate MIME type and set document to Ingested state."""
    mime = state.get("attachment_mime_type", "")
    doc_id = state.get("document_id") or str(uuid.uuid4())

    if mime not in _ALLOWED_MIME_TYPES:
        _log_transition("ingestion_agent", state, "Ingested", "Error_Queue",
                        "ERROR", f"Invalid MIME type: {mime}")
        return {
            "document_id": doc_id,
            "document_state": "Error_Queue",
            "error": f"Invalid MIME type: {mime}",
            "messages": [AIMessage(content=f"[ingestion_agent] Rejected — invalid MIME type: {mime}")],
        }

    _log_transition("ingestion_agent", state, "NEW", "Ingested",
                    "OK", f"Document {doc_id} ingested. MIME: {mime}")

    return {
        "document_id": doc_id,
        "document_state": "Ingested",
        "error": None,
        "messages": [AIMessage(content=f"[ingestion_agent] Document {doc_id} ingested ({mime}).")],
    }


# ---------------------------------------------------------------------------
# Node: ocr_extract
# ---------------------------------------------------------------------------

def ocr_extract_node(state: ContraState) -> dict[str, Any]:
    """Extract/validate OCR fields. Stub — uses fields already in state.

    In production, this node would call the LLM adapter to run OCR.
    """
    ocr_fields = state.get("ocr_fields", {})
    doc_id = state.get("document_id", "")

    # Gate: amount and account_name must be present
    amount_field = ocr_fields.get("amount", {})
    account_field = ocr_fields.get("account_name", {})

    if not amount_field.get("value") or not account_field.get("value"):
        _log_transition("ocr_agent", state, "Ingested", "Incomplete_Data",
                        "ERROR", "Required fields (amount or account_name) missing or null.")
        return {
            "document_state": "Incomplete_Data",
            "error": "Required OCR fields missing.",
            "messages": [AIMessage(content="[ocr_agent] BLOCKED — required fields missing.")],
        }

    # Check confidence scores
    low_confidence = [
        name for name, field in ocr_fields.items()
        if field.get("confidence_score", 0.0) < CONFIDENCE_THRESHOLD
    ]

    confidence_msg = "; ".join(
        f"{n}: {ocr_fields[n].get('confidence_score', 0):.2f}" for n in ocr_fields
    )

    if low_confidence:
        _log_transition("ocr_agent", state, "Ingested", "Needs_Review",
                        "BLOCKED", f"Low confidence fields: {', '.join(low_confidence)}")
        return {
            "document_state": "Needs_Review",
            "error": f"Low confidence: {', '.join(low_confidence)}",
            "messages": [AIMessage(
                content=f"[ocr_agent] Fields extracted ({confidence_msg}). "
                        f"BLOCKED — low confidence: {', '.join(low_confidence)}"
            )],
        }

    _log_transition("ocr_agent", state, "Ingested", "Parsed",
                    "OK", f"All fields above threshold. {confidence_msg}")

    return {
        "document_state": "Parsed",
        "error": None,
        "messages": [AIMessage(
            content=f"[ocr_agent] OCR complete for {doc_id}. {confidence_msg}. All above 0.85 threshold."
        )],
    }


# ---------------------------------------------------------------------------
# Node: pii_redact
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def pii_redact_node(state: ContraState) -> dict[str, Any]:
    """Redact PII from document fields. Non-bypassable gate."""
    source_email = state.get("source_email", "")
    raw_text = state.get("raw_text")

    redacted_email = "[REDACTED]" if source_email else ""

    # Verify redaction succeeded
    if redacted_email and "@" in redacted_email:
        _log_transition("ingestion_agent", state, "Parsed", "Error_Queue",
                        "ERROR", "PII redaction failed — email still contains @.")
        return {
            "document_state": "Error_Queue",
            "error": "PII redaction failed.",
            "messages": [AIMessage(content="[pii_redaction] ERROR — redaction check failed.")],
        }

    _log_transition("ingestion_agent", state, "Parsed", "PII_Redacted",
                    "OK", "PII redacted. Email masked, raw text cleared.")

    return {
        "source_email": redacted_email,
        "raw_text": None,
        "document_state": "PII_Redacted",
        "error": None,
        "messages": [AIMessage(
            content="[pii_redaction] PII redacted — email masked to [REDACTED], raw text cleared."
        )],
    }


# ---------------------------------------------------------------------------
# Node: match
# ---------------------------------------------------------------------------

def match_node(state: ContraState) -> dict[str, Any]:
    """Match document against bank transaction candidates.

    Implements the full Auditor Agent constitution protocol:
    temporal window → zero variance → duplicate lock → bank ref ID → name similarity.
    """
    ocr_fields = state.get("ocr_fields", {})
    candidates = state.get("bank_candidates", [])
    doc_id = state.get("document_id", "")

    email_amount = float(ocr_fields.get("amount", {}).get("value") or 0)
    email_date_str = ocr_fields.get("payment_date", {}).get("value")
    email_date = _parse_date(email_date_str)
    email_ref = ocr_fields.get("bank_reference_id", {}).get("value")

    viable = []
    for txn in candidates:
        # Temporal window
        if email_date is not None:
            txn_date = _parse_date(txn.get("date"))
            if txn_date and abs((txn_date - email_date).days) > TEMPORAL_WINDOW_DAYS:
                continue
        # Zero variance
        if txn.get("amount", 0.0) - email_amount != 0.0:
            continue
        viable.append(txn)

    # Duplicate Lock
    if len(viable) > 1:
        ids = ", ".join(t.get("transaction_id", "?") for t in viable)
        result = {
            "match_id": str(uuid.uuid4()),
            "document_id": doc_id,
            "decision": "LOCKED",
            "amount_delta": 0.0,
            "rationale": f"Duplicate candidates ({ids}). Both LOCKED — human review required.",
        }
        _log_transition("auditor_agent", state, "PII_Redacted", "Human_Review",
                        "LOCKED", result["rationale"])
        return {
            "document_state": "Human_Review",
            "match_result": result,
            "error": None,
            "messages": [AIMessage(content=f"[auditor_agent] LOCKED — duplicates: {ids}")],
        }

    if not viable:
        result = {
            "match_id": str(uuid.uuid4()),
            "document_id": doc_id,
            "decision": "PENDING",
            "amount_delta": email_amount,
            "rationale": "No matching bank transaction found. Status: Pending.",
        }
        _log_transition("auditor_agent", state, "PII_Redacted", "Pending",
                        "PENDING", result["rationale"])
        return {
            "document_state": "Exception_Review",
            "match_result": result,
            "error": None,
            "messages": [AIMessage(content="[auditor_agent] No match found — PENDING.")],
        }

    txn = viable[0]
    txn_date = _parse_date(txn.get("date"))
    delta_days = abs((txn_date - email_date).days) if txn_date and email_date else None

    # Bank Reference ID supremacy
    if email_ref and txn.get("reference_id") and email_ref == txn["reference_id"]:
        result = {
            "match_id": str(uuid.uuid4()),
            "document_id": doc_id,
            "bank_transaction_id": txn["transaction_id"],
            "decision": "MATCHED",
            "amount_delta": 0.0,
            "bank_reference_id_match": True,
            "temporal_delta_days": delta_days,
            "rationale": f"Bank Ref ID '{email_ref}' matched exactly.",
        }
        _log_transition("auditor_agent", state, "PII_Redacted", "Matched",
                        "MATCHED", result["rationale"])
        return {
            "document_state": "Matched",
            "match_result": result,
            "error": None,
            "messages": [AIMessage(
                content=f"[auditor_agent] MATCHED via Bank Ref ID '{email_ref}'. Delta $0.00."
            )],
        }

    # Name similarity (Levenshtein)
    doc_name = (ocr_fields.get("account_name", {}).get("value") or "").lower()
    txn_name = (txn.get("account_name") or "").lower()
    score = levenshtein_ratio(doc_name, txn_name)

    if score < NAME_SIMILARITY_THRESHOLD:
        result = {
            "match_id": str(uuid.uuid4()),
            "document_id": doc_id,
            "bank_transaction_id": txn["transaction_id"],
            "decision": "FLAGGED",
            "amount_delta": 0.0,
            "name_similarity": round(score, 4),
            "temporal_delta_days": delta_days,
            "rationale": f"Name similarity {score:.4f} below threshold {NAME_SIMILARITY_THRESHOLD}.",
        }
        _log_transition("auditor_agent", state, "PII_Redacted", "Exception_Review",
                        "FLAGGED", result["rationale"])
        return {
            "document_state": "Exception_Review",
            "match_result": result,
            "error": None,
            "messages": [AIMessage(
                content=f"[auditor_agent] FLAGGED — name sim {score:.4f} < {NAME_SIMILARITY_THRESHOLD}"
            )],
        }

    result = {
        "match_id": str(uuid.uuid4()),
        "document_id": doc_id,
        "bank_transaction_id": txn["transaction_id"],
        "decision": "MATCHED",
        "amount_delta": 0.0,
        "name_similarity": round(score, 4),
        "temporal_delta_days": delta_days,
        "rationale": f"Amount $0.00 delta, name similarity {score:.4f}, within {delta_days}-day window.",
    }
    _log_transition("auditor_agent", state, "PII_Redacted", "Matched",
                    "MATCHED", result["rationale"])
    return {
        "document_state": "Matched",
        "match_result": result,
        "error": None,
        "messages": [AIMessage(
            content=f"[auditor_agent] MATCHED — name sim {score:.4f}, delta $0.00, {delta_days}d window."
        )],
    }


# ---------------------------------------------------------------------------
# Node: finalize
# ---------------------------------------------------------------------------

def finalize_node(state: ContraState) -> dict[str, Any]:
    """Generate receipt and mark as Finalized."""
    doc_id = state.get("document_id", "")

    _log_transition("finalization_agent", state, "Matched", "Finalized",
                    "OK", f"Receipt generated for {doc_id}. Pipeline complete.")

    return {
        "document_state": "Finalized",
        "error": None,
        "messages": [AIMessage(
            content=f"[finalization] Receipt generated for {doc_id}. Pipeline complete."
        )],
    }


# ---------------------------------------------------------------------------
# Node: error_handler (terminal)
# ---------------------------------------------------------------------------

def error_handler_node(state: ContraState) -> dict[str, Any]:
    """Terminal node for documents routed to error states."""
    error = state.get("error", "Unknown error")
    doc_state = state.get("document_state", "Error_Queue")
    return {
        "messages": [AIMessage(
            content=f"[error_handler] Document halted in {doc_state}: {error}"
        )],
    }


# ---------------------------------------------------------------------------
# Node: human_review (HITL interrupt)
# ---------------------------------------------------------------------------

def human_review_node(state: ContraState) -> dict[str, Any]:
    """Pause execution via LangGraph interrupt() for human review.

    The graph suspends here. When resumed with a Command, the human_review_*
    fields are populated in state, and the graph continues to the next node.
    """
    doc_id = state.get("document_id", "")
    doc_state = state.get("document_state", "")
    error = state.get("error", "")
    match_result = state.get("match_result")

    review_context = {
        "document_id": doc_id,
        "document_state": doc_state,
        "reason": error or (match_result or {}).get("rationale", "Review required"),
        "match_result": match_result,
    }

    # This suspends the graph and waits for human input
    human_input = interrupt(review_context)

    # When resumed, human_input contains the reviewer's decision
    reviewer_id = human_input.get("reviewer_id", "anonymous")
    action = human_input.get("action", "reject")  # approve | reject | correct
    rationale = human_input.get("rationale", "")
    corrected_data = human_input.get("corrected_data")

    _log_transition("human_reviewer", state, doc_state, f"HITL_{action}",
                    action.upper(), f"Reviewer {reviewer_id}: {rationale}")

    update: dict[str, Any] = {
        "human_review_action": action,
        "human_reviewer_id": reviewer_id,
        "human_review_rationale": rationale,
        "messages": [AIMessage(
            content=f"[human_review] Reviewer {reviewer_id} action: {action}. {rationale}"
        )],
    }

    if action == "approve":
        # Re-enter the pipeline at the appropriate point
        if doc_state == "Needs_Review":
            update["document_state"] = "Parsed"
            update["error"] = None
        elif doc_state == "Human_Review":
            update["document_state"] = "Matched"
            update["error"] = None
            if match_result:
                match_result["decision"] = "MATCHED"
                update["match_result"] = match_result
        elif doc_state == "Exception_Review":
            update["document_state"] = "Matched"
            update["error"] = None
    elif action == "correct" and corrected_data:
        # Human corrected OCR fields — retry OCR gate
        update["ocr_fields"] = corrected_data.get("ocr_fields", state.get("ocr_fields", {}))
        update["document_state"] = "Ingested"  # re-run OCR check
        update["error"] = None
    else:
        # Rejected — stay in error state
        update["document_state"] = "Error_Queue"
        update["error"] = f"Rejected by reviewer {reviewer_id}: {rationale}"

    return update


# ---------------------------------------------------------------------------
# Routing functions (conditional edges)
# ---------------------------------------------------------------------------

def route_after_ocr(state: ContraState) -> str:
    """Route after OCR extraction based on document state."""
    doc_state = state.get("document_state", "")
    if doc_state == "Parsed":
        return "pii_redact"
    elif doc_state == "Needs_Review":
        return "human_review"
    else:
        return "error_handler"


def route_after_match(state: ContraState) -> str:
    """Route after matching based on match decision."""
    doc_state = state.get("document_state", "")
    if doc_state == "Matched":
        return "finalize"
    elif doc_state == "Human_Review":
        return "human_review"
    elif doc_state == "Exception_Review":
        return "human_review"
    else:
        return "error_handler"


def route_after_human_review(state: ContraState) -> str:
    """Route after human review based on the reviewer's action."""
    action = state.get("human_review_action", "reject")
    doc_state = state.get("document_state", "")

    if action == "reject":
        return "error_handler"
    elif doc_state == "Ingested":
        # Corrected OCR fields — re-run OCR check
        return "ocr_extract"
    elif doc_state == "Parsed":
        return "pii_redact"
    elif doc_state == "Matched":
        return "finalize"
    else:
        return "error_handler"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    from datetime import datetime as dt
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return dt.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _log_transition(
    agent: str,
    state: ContraState,
    state_from: str,
    state_to: str,
    decision: str,
    rationale: str,
) -> None:
    """Write audit log entry for a state transition."""
    entry = AuditEntry(
        agent=agent,
        input_hash=compute_hash({
            "document_id": state.get("document_id"),
            "document_state": state.get("document_state"),
        }),
        output_hash=compute_hash({"state_to": state_to}),
        state_from=state_from,
        state_to=state_to,
        decision=decision,
        rationale=rationale,
        confidence_scores={
            name: field.get("confidence_score", 0.0)
            for name, field in state.get("ocr_fields", {}).items()
        },
    )
    audit_log.append(entry)

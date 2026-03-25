"""Shared state for the LangGraph reconciliation pipeline.

All nodes operate on ContraState — a TypedDict that LangGraph manages.
Nodes receive the full state and return a partial update dict.
"""

from __future__ import annotations

from typing import Annotated, Any

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


def _replace(existing: Any, new: Any) -> Any:
    """Reducer that replaces old value with new value (last-write-wins)."""
    return new


class BankTransactionDict(TypedDict, total=False):
    """Bank statement line item carried through the graph."""

    transaction_id: str
    account_name: str
    amount: float
    date: str
    reference_id: str | None


class FileRecord(TypedDict, total=False):
    """Per-file tracking record for batch processing."""

    file_id: str
    source_path: str
    work_path: str
    mime_type: str
    status: str  # pending | ocr_done | enriched | error
    ocr_fields: dict[str, dict[str, Any]]
    ocr_json_path: str | None
    error: str | None


class ContraState(TypedDict, total=False):
    """Shared state flowing through the reconciliation graph.

    Every field uses a reducer:
    - Annotated[..., _replace] → last-write-wins (most fields)
    - messages uses LangGraph's built-in add_messages reducer
    """

    # ── Document fields ──
    document_id: Annotated[str, _replace]
    source_email: Annotated[str, _replace]
    attachment_mime_type: Annotated[str, _replace]
    raw_text: Annotated[str | None, _replace]

    # File tracking (single-file — kept for backward compat)
    source_file_path: Annotated[str | None, _replace]
    work_file_path: Annotated[str | None, _replace]

    # ── Batch processing fields ──
    batch_id: Annotated[str | None, _replace]
    file_records: Annotated[list[FileRecord], _replace]
    spreadsheet_path: Annotated[str | None, _replace]
    review_spreadsheet_path: Annotated[str | None, _replace]

    # OCR extracted fields: {field_name: {"value": str|None, "confidence_score": float}}
    ocr_fields: Annotated[dict[str, dict[str, Any]], _replace]

    # Current document state in the pipeline
    document_state: Annotated[str, _replace]

    # Bank transaction candidates for matching
    bank_candidates: Annotated[list[BankTransactionDict], _replace]

    # Match result from auditor (serialised MatchResult dict)
    match_result: Annotated[dict[str, Any] | None, _replace]

    # Error info when routed to an error node
    error: Annotated[str | None, _replace]

    # HITL: review fields set by human when resuming from interrupt
    human_review_action: Annotated[str | None, _replace]  # "approve" | "reject" | "correct"
    human_review_data: Annotated[dict[str, Any] | None, _replace]
    human_reviewer_id: Annotated[str | None, _replace]
    human_review_rationale: Annotated[str | None, _replace]

    # LangChain message history (for agent reasoning trace)
    messages: Annotated[list, add_messages]

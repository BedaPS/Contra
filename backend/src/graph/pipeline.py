"""LangGraph StateGraph definition for the Contra reconciliation pipeline.

Graph topology:
    ingest → ocr_extract ─┬─→ pii_redact → match ─┬─→ finalize → END
                           │                        │
                           └─→ human_review ←───────┘
                           │        │
                           │        ├─→ ocr_extract  (correct → retry)
                           │        ├─→ pii_redact   (approve Needs_Review)
                           │        ├─→ finalize     (approve match)
                           │        └─→ error_handler (reject)
                           │
                           └─→ error_handler → END

Human-in-the-loop: human_review node uses interrupt() to pause the graph.
Resume with Command(resume={...}) to continue execution.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.graph.nodes import (
    error_handler_node,
    finalize_node,
    human_review_node,
    ingest_node,
    match_node,
    ocr_extract_node,
    pii_redact_node,
    route_after_human_review,
    route_after_match,
    route_after_ocr,
)
from src.graph.state import ContraState


def build_pipeline() -> StateGraph:
    """Construct and compile the reconciliation StateGraph.

    Returns a compiled graph with checkpointing enabled for HITL support.
    """
    graph = StateGraph(ContraState)

    # ── Add nodes ──
    graph.add_node("ingest", ingest_node)
    graph.add_node("ocr_extract", ocr_extract_node)
    graph.add_node("pii_redact", pii_redact_node)
    graph.add_node("match", match_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("error_handler", error_handler_node)
    graph.add_node("human_review", human_review_node)

    # ── Entry point ──
    graph.set_entry_point("ingest")

    # ── Edges ──
    # After ingest, always go to OCR (error is caught inside the node)
    graph.add_conditional_edges(
        "ingest",
        lambda state: "error_handler" if state.get("document_state") == "Error_Queue" else "ocr_extract",
        {"ocr_extract": "ocr_extract", "error_handler": "error_handler"},
    )

    # After OCR: Parsed → pii_redact | Needs_Review → human_review | else → error_handler
    graph.add_conditional_edges("ocr_extract", route_after_ocr, {
        "pii_redact": "pii_redact",
        "human_review": "human_review",
        "error_handler": "error_handler",
    })

    # After PII redaction, always go to match
    graph.add_conditional_edges(
        "pii_redact",
        lambda state: "error_handler" if state.get("document_state") == "Error_Queue" else "match",
        {"match": "match", "error_handler": "error_handler"},
    )

    # After match: Matched → finalize | Human_Review/Exception → human_review | else → error
    graph.add_conditional_edges("match", route_after_match, {
        "finalize": "finalize",
        "human_review": "human_review",
        "error_handler": "error_handler",
    })

    # Human review can route back into the pipeline (cyclic) or to error
    graph.add_conditional_edges("human_review", route_after_human_review, {
        "ocr_extract": "ocr_extract",
        "pii_redact": "pii_redact",
        "finalize": "finalize",
        "error_handler": "error_handler",
    })

    # Terminal nodes
    graph.add_edge("finalize", END)
    graph.add_edge("error_handler", END)

    return graph


def compile_pipeline(checkpointer: MemorySaver | None = None):
    """Build and compile the graph with an optional checkpointer.

    If no checkpointer is provided, an in-memory MemorySaver is used
    (suitable for development; swap for a persistent store in production).
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    graph = build_pipeline()
    return graph.compile(checkpointer=checkpointer)


# Module-level compiled graph (lazy singleton)
_compiled_graph = None


def get_pipeline():
    """Return the compiled pipeline graph (singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = compile_pipeline()
    return _compiled_graph

"""LangGraph StateGraph definition for the Contra reconciliation pipeline.

Graph topology:
    ingest → ocr_extract ─┬─→ enrich → build_spreadsheet ─[HITL]─→ match ─┬─→ finalize → END
                           │                                                │
                           └─→ human_review ←───────────────────────────────┘
                           │        │
                           │        ├─→ ocr_extract  (correct → retry)
                           │        ├─→ enrich       (approve Needs_Review)
                           │        ├─→ finalize     (approve match)
                           │        └─→ error_handler (reject)
                           │
                           └─→ error_handler → END

Human-in-the-loop:
  - build_spreadsheet uses interrupt() to pause for spreadsheet review.
  - human_review node uses interrupt() for OCR/match/exception review.
  Resume with Command(resume={...}) to continue execution.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.graph.nodes import (
    build_spreadsheet_node,
    enrich_node,
    error_handler_node,
    finalize_node,
    human_review_node,
    ingest_node,
    match_node,
    ocr_extract_node,
    route_after_human_review,
    route_after_match,
    route_after_ocr,
)
from src.graph.state import ContraState


# Ordered list of happy-path node names (used by topology API and UI)
HAPPY_PATH_NODES: list[dict[str, str]] = [
    {"id": "ingest", "label": "Ingestion"},
    {"id": "ocr_extract", "label": "OCR Extract"},
    {"id": "enrich", "label": "Enrichment"},
    {"id": "build_spreadsheet", "label": "Build Spreadsheet"},
    {"id": "spreadsheet_review", "label": "Spreadsheet Review"},
    {"id": "match", "label": "Matching"},
    {"id": "finalize", "label": "Finalization"},
]

# Edges between nodes (source → target)
PIPELINE_EDGES: list[dict[str, str]] = [
    {"source": "ingest", "target": "ocr_extract"},
    {"source": "ocr_extract", "target": "enrich", "condition": "Parsed"},
    {"source": "ocr_extract", "target": "human_review", "condition": "Needs_Review"},
    {"source": "ocr_extract", "target": "error_handler", "condition": "Error"},
    {"source": "enrich", "target": "build_spreadsheet"},
    {"source": "build_spreadsheet", "target": "spreadsheet_review", "condition": "HITL pause"},
    {"source": "spreadsheet_review", "target": "match", "condition": "Approved"},
    {"source": "spreadsheet_review", "target": "error_handler", "condition": "Rejected"},
    {"source": "match", "target": "finalize", "condition": "Matched"},
    {"source": "match", "target": "human_review", "condition": "Review"},
    {"source": "match", "target": "error_handler", "condition": "Error"},
    {"source": "finalize", "target": "__end__"},
    {"source": "error_handler", "target": "__end__"},
    {"source": "human_review", "target": "ocr_extract", "condition": "correct"},
    {"source": "human_review", "target": "enrich", "condition": "approve"},
    {"source": "human_review", "target": "finalize", "condition": "approve_match"},
    {"source": "human_review", "target": "error_handler", "condition": "reject"},
]

# Support nodes (not on the happy path, but present in the graph)
SUPPORT_NODES: list[dict[str, str]] = [
    {"id": "human_review", "label": "Human Review"},
    {"id": "error_handler", "label": "Error Handler"},
]


def build_pipeline() -> StateGraph:
    """Construct and compile the reconciliation StateGraph.

    Returns a compiled graph with checkpointing enabled for HITL support.
    """
    graph = StateGraph(ContraState)

    # ── Add nodes ──
    graph.add_node("ingest", ingest_node)
    graph.add_node("ocr_extract", ocr_extract_node)
    graph.add_node("enrich", enrich_node)
    graph.add_node("build_spreadsheet", build_spreadsheet_node)
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

    # After OCR: Parsed → enrich | Needs_Review → human_review | else → error_handler
    graph.add_conditional_edges("ocr_extract", route_after_ocr, {
        "enrich": "enrich",
        "human_review": "human_review",
        "error_handler": "error_handler",
    })

    # After enrichment, go to build_spreadsheet
    graph.add_conditional_edges(
        "enrich",
        lambda state: "error_handler" if state.get("document_state") == "Error_Queue" else "build_spreadsheet",
        {"build_spreadsheet": "build_spreadsheet", "error_handler": "error_handler"},
    )

    # After spreadsheet (includes HITL interrupt inside node):
    # Approved → match | Rejected → error_handler
    graph.add_conditional_edges(
        "build_spreadsheet",
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
        "enrich": "enrich",
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


def get_topology() -> dict:
    """Return the pipeline topology for the UI to render dynamically.

    Returns a dict with:
      - nodes: ordered happy-path nodes [{id, label}, ...]
      - supportNodes: auxiliary nodes [{id, label}, ...]
      - edges: [{source, target, condition?}, ...]
    """
    return {
        "nodes": HAPPY_PATH_NODES,
        "supportNodes": SUPPORT_NODES,
        "edges": PIPELINE_EDGES,
    }

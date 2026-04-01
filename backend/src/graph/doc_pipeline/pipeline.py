"""LangGraph StateGraph for the document processing pipeline.

Graph topology:
    classifier_node → extractor_node → normaliser_node → validator_node
                                                                     │
                                                             excel_writer_node → END
    error_node ← (any node on failure)

All nodes that encounter an error set `state["error"]` before returning.
Conditional edges route to error_node when error is present.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.graph.doc_pipeline.nodes import (
    classifier_node,
    error_node,
    excel_writer_node,
    extractor_node,
    normaliser_node,
    validator_node,
)
from src.graph.doc_pipeline.state import DocPipelineState


def _has_error(state: DocPipelineState) -> str:
    """Route to error_node if an error is present, otherwise continue."""
    return "error_node" if state.get("error") else "continue"


def build_doc_pipeline() -> StateGraph:
    """Construct and compile the document processing StateGraph.

    Returns a compiled graph. No checkpointing is used — each file invocation
    is a single, synchronous run with no HITL interrupts in this pipeline.
    """
    graph = StateGraph(DocPipelineState)

    # ── Add nodes ──
    graph.add_node("classifier_node", classifier_node)
    graph.add_node("extractor_node", extractor_node)
    graph.add_node("normaliser_node", normaliser_node)
    graph.add_node("validator_node", validator_node)
    graph.add_node("excel_writer_node", excel_writer_node)
    graph.add_node("error_node", error_node)

    # ── Entry point ──
    graph.set_entry_point("classifier_node")

    # ── Conditional edges: route to error_node on failure ──
    graph.add_conditional_edges(
        "classifier_node",
        _has_error,
        {"error_node": "error_node", "continue": "extractor_node"},
    )
    graph.add_conditional_edges(
        "extractor_node",
        _has_error,
        {"error_node": "error_node", "continue": "normaliser_node"},
    )

    # normaliser_node does not call LLM — failures are silently handled inline
    graph.add_edge("normaliser_node", "validator_node")
    graph.add_edge("validator_node", "excel_writer_node")
    graph.add_edge("excel_writer_node", END)
    graph.add_edge("error_node", END)

    return graph.compile()


# Module-level compiled graph singleton — import and call directly in tests / RunService
_doc_pipeline: StateGraph | None = None


def get_doc_pipeline() -> StateGraph:
    """Return the module-level compiled DocPipeline graph (singleton)."""
    global _doc_pipeline
    if _doc_pipeline is None:
        _doc_pipeline = build_doc_pipeline()
    return _doc_pipeline

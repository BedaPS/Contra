"""T041: Validate DocPipeline graph Mermaid output (SC-008).

Calls get_doc_pipeline().get_graph().draw_mermaid() and asserts it
returns a non-empty string containing the expected node names without
raising any exception.
"""

from __future__ import annotations

import pytest


class TestDocPipelineMermaidOutput:
    """SC-008: DocPipeline graph Mermaid output must render without error."""

    def test_draw_mermaid_returns_non_empty_string(self):
        """draw_mermaid() should return a non-empty Mermaid diagram string."""
        from src.graph.doc_pipeline.pipeline import build_doc_pipeline

        graph = build_doc_pipeline()
        mermaid = graph.get_graph().draw_mermaid()

        assert isinstance(mermaid, str), "draw_mermaid() should return a string"
        assert len(mermaid) > 0, "draw_mermaid() should return a non-empty string"

    def test_draw_mermaid_contains_all_node_names(self):
        """The Mermaid diagram should reference all 6 pipeline nodes."""
        from src.graph.doc_pipeline.pipeline import build_doc_pipeline

        expected_nodes = [
            "classifier_node",
            "extractor_node",
            "normaliser_node",
            "validator_node",
            "excel_writer_node",
            "error_node",
        ]

        graph = build_doc_pipeline()
        mermaid = graph.get_graph().draw_mermaid()

        for node in expected_nodes:
            assert node in mermaid, (
                f"Node '{node}' not found in Mermaid diagram output"
            )

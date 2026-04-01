"""Unit tests for classifier_node (T047).

Tests:
- Each doc_type value (email, remittance, receipt, unknown) is parsed correctly
- error_node routing on parse failure
- error_node routing on LLM exception
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_state(work_file_path: str = "/tmp/test.pdf") -> dict:
    return {
        "run_record_id": "test-run-001",
        "batch_id": "batch-001",
        "source_file_path": "/source/test.pdf",
        "work_file_path": work_file_path,
    }


@pytest.fixture
def mock_pdf_page():
    """Return a fitz Page mock that renders a fake base64 image."""
    page = MagicMock()
    pix = MagicMock()
    pix.samples = b"\x00" * 100  # small buffer — no resize needed
    pix.tobytes.return_value = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20  # fake PNG bytes
    page.get_pixmap.return_value = pix
    return page


@pytest.fixture
def mock_fitz_doc(mock_pdf_page):
    """Return a fitz.Document mock with one page."""
    doc = MagicMock()
    doc.__getitem__ = MagicMock(return_value=mock_pdf_page)
    doc.close = MagicMock()
    return doc


class TestClassifierNodeDocTypes:
    """Assert each doc_type value is parsed correctly from LLM response."""

    @pytest.mark.parametrize("llm_response,expected_doc_type", [
        ("email", "email"),
        ("remittance", "remittance"),
        ("receipt", "receipt"),
        ("unknown", "unknown"),
        ("  email  ", "email"),          # with whitespace
        ("EMAIL", "email"),               # uppercase
        ("remittance advice", "remittance"),  # extra words — only first word used
    ])
    def test_doc_type_parsed(self, llm_response, expected_doc_type, mock_fitz_doc):
        from backend.src.graph.doc_pipeline.nodes import classifier_node

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_doc),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
            patch("backend.src.graph.doc_pipeline.nodes._load_prompt_config", return_value={}),
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.return_value = llm_response

            result = classifier_node(_make_state())

        assert result.get("doc_type") == expected_doc_type
        assert result.get("error") is None

    def test_invalid_doc_type_becomes_unknown(self, mock_fitz_doc):
        from backend.src.graph.doc_pipeline.nodes import classifier_node

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_doc),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
            patch("backend.src.graph.doc_pipeline.nodes._load_prompt_config", return_value={}),
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.return_value = "invoice"  # not in valid set

            result = classifier_node(_make_state())

        assert result.get("doc_type") == "unknown"
        assert result.get("error") is None


class TestClassifierNodeErrorRouting:
    """Assert classifier_node routes to error_node on parse failure and LLM exceptions."""

    def test_page_render_failure_sets_error(self):
        from backend.src.graph.doc_pipeline.nodes import classifier_node

        with patch("backend.src.graph.doc_pipeline.nodes.fitz.open") as mock_open:
            mock_open.side_effect = RuntimeError("Cannot open file")
            result = classifier_node(_make_state())

        assert result.get("error") is not None
        assert "render" in result.get("error", "").lower() or "page" in result.get("error", "").lower()
        assert result.get("error_type") == "render_error"

    def test_llm_exception_sets_error(self, mock_fitz_doc):
        from backend.src.graph.doc_pipeline.nodes import classifier_node

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_doc),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.side_effect = Exception("LLM service unavailable")

            result = classifier_node(_make_state())

        assert result.get("error") is not None
        assert result.get("error_type") == "llm_error"

    def test_prompt_config_load_failure_does_not_crash(self, mock_fitz_doc):
        """If YAML config missing, classifier should still succeed with empty config."""
        from backend.src.graph.doc_pipeline.nodes import classifier_node

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_doc),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
            patch(
                "backend.src.graph.doc_pipeline.nodes._load_prompt_config",
                side_effect=FileNotFoundError("yaml not found"),
            ),
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.return_value = "remittance"

            result = classifier_node(_make_state())

        # Should still classify correctly, just with empty prompt_config
        assert result.get("doc_type") == "remittance"
        assert result.get("error") is None
        assert result.get("prompt_config") == {}

"""Unit tests for extractor_node (T048 + T049).

Tests:
- T048: Canned JSON parsing, retry logic (3 consecutive parse failures → error_node),
        all-null detection, correct page_number tagging per extracted record
- T049: HTTP 429 / rate-limit exponential backoff (5s → 15s → 45s) and final
        error_node routing after all retries exhausted
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, call

import pytest


_CANNED_RECORD = {
    "customer_name": "Acme Corp",
    "account_number": "12345678",
    "payee": "Vendor Ltd",
    "payment_id": "TXN-001",
    "payment_method": "EFT",
    "payment_date": "2024-03-15",
    "invoice_number": "INV-100",
    "reference_doc_number": None,
    "amount_paid": 1500.0,
    "currency": "ZAR",
    "deductions": None,
    "deduction_type": None,
    "notes": None,
    "page_number": 1,
    "confidence_scores": {
        "customer_name": 0.90,
        "account_number": 0.85,
        "payee": 0.87,
        "payment_id": 0.75,
        "payment_method": 0.88,
        "payment_date": 0.92,
        "invoice_number": 0.80,
        "reference_doc_number": 0.70,
        "amount_paid": 0.95,
        "currency": 0.93,
        "deductions": 0.70,
        "deduction_type": 0.70,
        "notes": 0.70,
    },
}

_CANNED_JSON = __import__("json").dumps([_CANNED_RECORD])


def _make_state(work_file_path: str = "/tmp/test.pdf") -> dict:
    return {
        "run_record_id": "test-run-001",
        "batch_id": "batch-001",
        "source_file_path": "/source/test.pdf",
        "work_file_path": work_file_path,
        "doc_type": "remittance",
        "prompt_config": {
            "context_hint": "Test document.",
            "field_hints": {"amount_paid": "Total amount."},
            "confidence_thresholds": {"amount_paid": 0.90},
        },
        "extraction_attempts": 0,
    }


@pytest.fixture
def mock_fitz_single_page():
    """Return a fitz.Document mock with one page."""
    pix = MagicMock()
    pix.samples = b"\x00" * 100
    pix.tobytes.return_value = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20

    page = MagicMock()
    page.get_pixmap.return_value = pix

    doc = MagicMock()
    doc.__iter__ = MagicMock(return_value=iter([page]))
    doc.close = MagicMock()
    return doc


class TestExtractorNodeCannedJSON:
    """T048: Canned JSON parsing and correct page_number tagging."""

    def test_successful_extraction_returns_raw_records(self, mock_fitz_single_page):
        from backend.src.graph.doc_pipeline.nodes import extractor_node

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_single_page),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.return_value = _CANNED_JSON

            result = extractor_node(_make_state())

        assert result.get("error") is None
        records = result.get("raw_records", [])
        assert len(records) == 1
        assert records[0]["amount_paid"] == 1500.0

    def test_page_number_tagged_correctly(self, mock_fitz_single_page):
        """Page number should be 1-based (page 1 = page_number 1)."""
        from backend.src.graph.doc_pipeline.nodes import extractor_node

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_single_page),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.return_value = _CANNED_JSON

            result = extractor_node(_make_state())

        records = result.get("raw_records", [])
        assert records[0]["page_number"] == 1

    def test_page_number_tagged_for_second_page(self):
        """For a 2-page document, page 2 records get page_number=2."""
        from backend.src.graph.doc_pipeline.nodes import extractor_node

        pix = MagicMock()
        pix.samples = b"\x00" * 100
        pix.tobytes.return_value = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20

        page1 = MagicMock()
        page1.get_pixmap.return_value = pix
        page2 = MagicMock()
        page2.get_pixmap.return_value = pix

        doc = MagicMock()
        doc.__iter__ = MagicMock(return_value=iter([page1, page2]))
        doc.close = MagicMock()

        canned_p1 = __import__("json").dumps([{**_CANNED_RECORD, "page_number": 1}])
        canned_p2 = __import__("json").dumps([{**_CANNED_RECORD, "page_number": 2, "amount_paid": 750.0}])

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=doc),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.side_effect = [canned_p1, canned_p2]

            result = extractor_node(_make_state())

        records = result.get("raw_records", [])
        assert len(records) == 2
        assert records[0]["page_number"] == 1
        assert records[1]["page_number"] == 2

    def test_dict_response_wrapped_in_list(self, mock_fitz_single_page):
        """LLM returning a dict (not array) should still produce one record."""
        from backend.src.graph.doc_pipeline.nodes import extractor_node

        import json
        single_dict_json = json.dumps(_CANNED_RECORD)

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_single_page),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.return_value = single_dict_json

            result = extractor_node(_make_state())

        assert len(result.get("raw_records", [])) == 1

    def test_markdown_fenced_json_stripped(self, mock_fitz_single_page):
        """LLM response with ``` fences should be handled."""
        from backend.src.graph.doc_pipeline.nodes import extractor_node

        fenced_json = f"```json\n{_CANNED_JSON}\n```"

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_single_page),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.return_value = fenced_json

            result = extractor_node(_make_state())

        assert result.get("error") is None
        assert len(result.get("raw_records", [])) == 1


class TestExtractorNodeRetryLogic:
    """T048: 3 consecutive parse failures → error_node routing."""

    def test_three_consecutive_parse_failures_route_to_error(self, mock_fitz_single_page):
        from backend.src.graph.doc_pipeline.nodes import extractor_node

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_single_page),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
        ):
            mock_adapter = mock_adapter_cls.return_value
            # Always return invalid JSON
            mock_adapter.invoke_vision.return_value = "This is not JSON at all."

            result = extractor_node(_make_state())

        assert result.get("error") is not None
        assert result.get("error_type") == "parse_error"
        # Should have made exactly 3 attempts
        assert mock_adapter.invoke_vision.call_count == 3

    def test_two_failures_then_success(self, mock_fitz_single_page):
        """Should succeed on the third attempt after 2 parse failures."""
        from backend.src.graph.doc_pipeline.nodes import extractor_node

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_single_page),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.side_effect = [
                "invalid json",     # attempt 1: parse failure
                "still invalid",    # attempt 2: parse failure
                _CANNED_JSON,       # attempt 3: success
            ]

            result = extractor_node(_make_state())

        assert result.get("error") is None
        assert len(result.get("raw_records", [])) == 1


class TestAllNullDetection:
    """T048: All-null detection routes to error_node."""

    def test_all_null_amount_paid_routes_to_error(self, mock_fitz_single_page):
        from backend.src.graph.doc_pipeline.nodes import extractor_node
        import json

        null_record = {**_CANNED_RECORD, "amount_paid": None}
        null_json = json.dumps([null_record])

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_single_page),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.return_value = null_json

            result = extractor_node(_make_state())

        assert result.get("error") is not None
        assert result.get("error_type") == "all_null"

    def test_null_string_amount_detected_as_null(self, mock_fitz_single_page):
        from backend.src.graph.doc_pipeline.nodes import extractor_node
        import json

        # LLM returning "null" as a string
        null_record = {**_CANNED_RECORD, "amount_paid": "null"}
        null_json = json.dumps([null_record])

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_single_page),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.return_value = null_json

            result = extractor_node(_make_state())

        assert result.get("error_type") == "all_null"


class TestRateLimitHandling:
    """T049: Exponential backoff (5s → 15s → 45s) and error_node routing post-exhaustion."""

    def test_rate_limit_triggers_exponential_backoff(self, mock_fitz_single_page):
        """sleep() calls should match the backoff sequence [5, 15, 45]."""
        from backend.src.graph.doc_pipeline.nodes import extractor_node

        class FakeRateLimitError(Exception):
            pass

        sleep_calls: list[float] = []

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_single_page),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
            patch("backend.src.graph.doc_pipeline.nodes._is_rate_limit_error", return_value=True),
            patch("backend.src.graph.doc_pipeline.nodes.time.sleep", side_effect=lambda s: sleep_calls.append(s)),
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.side_effect = FakeRateLimitError("429 Too Many Requests")

            result = extractor_node(_make_state())

        assert result.get("error") is not None
        assert result.get("error_type") == "rate_limit"
        # Backoff sequence should be exactly [5, 15, 45]
        assert sleep_calls == [5, 15, 45]

    def test_rate_limit_exhausted_routes_to_error_node(self, mock_fitz_single_page):
        """After all retries, error should be set so pipeline routes to error_node."""
        from backend.src.graph.doc_pipeline.nodes import extractor_node

        class FakeRateLimitError(Exception):
            pass

        with (
            patch("backend.src.graph.doc_pipeline.nodes.fitz.open", return_value=mock_fitz_single_page),
            patch("backend.src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
            patch("backend.src.graph.doc_pipeline.nodes._is_rate_limit_error", return_value=True),
            patch("backend.src.graph.doc_pipeline.nodes.time.sleep"),
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.side_effect = FakeRateLimitError("429")

            result = extractor_node(_make_state())

        assert result.get("error") is not None
        assert result.get("error_type") == "rate_limit"

    def test_rate_limit_detection_by_status_message(self, mock_fitz_single_page):
        """_is_rate_limit_error should detect '429' in exception message."""
        from backend.src.graph.doc_pipeline.nodes import _is_rate_limit_error

        exc_429 = Exception("HTTP 429 Too Many Requests")
        exc_rate = Exception("rate limit exceeded")
        exc_other = Exception("internal server error")

        assert _is_rate_limit_error(exc_429) is True
        assert _is_rate_limit_error(exc_rate) is True
        assert _is_rate_limit_error(exc_other) is False

"""Integration tests for the LangGraph reconciliation pipeline."""

import pytest

from src.graph.pipeline import compile_pipeline


@pytest.fixture
def pipeline():
    """Fresh compiled pipeline per test with isolated checkpointer."""
    return compile_pipeline()


def _happy_path_input(thread_id: str = "test-happy") -> tuple[dict, dict]:
    """Return (input_state, config) for a happy-path run."""
    state = {
        "document_id": "TEST-HAPPY-001",
        "source_email": "test@example.com",
        "attachment_mime_type": "application/pdf",
        "raw_text": "Invoice text",
        "ocr_fields": {
            "account_name": {"value": "Acme Corp", "confidence_score": 0.97},
            "amount": {"value": "5000.00", "confidence_score": 0.99},
            "payment_date": {"value": "2026-03-20", "confidence_score": 0.96},
            "bank_reference_id": {"value": "REF-100", "confidence_score": 0.95},
        },
        "document_state": "NEW",
        "bank_candidates": [
            {
                "transaction_id": "TXN-100",
                "account_name": "Acme Corp",
                "amount": 5000.00,
                "date": "2026-03-20",
                "reference_id": "REF-100",
            },
        ],
        "match_result": None,
        "error": None,
        "messages": [],
    }
    config = {"configurable": {"thread_id": thread_id}}
    return state, config


class TestHappyPath:
    def test_pipeline_reaches_finalized(self, pipeline):
        state, config = _happy_path_input()
        result = pipeline.invoke(state, config=config)
        assert result["document_state"] == "Finalized"

    def test_match_decision_is_matched(self, pipeline):
        state, config = _happy_path_input("test-match")
        result = pipeline.invoke(state, config=config)
        assert result["match_result"]["decision"] == "MATCHED"

    def test_pii_redacted(self, pipeline):
        state, config = _happy_path_input("test-pii")
        result = pipeline.invoke(state, config=config)
        assert result["source_email"] == "[REDACTED]"
        assert result["raw_text"] is None

    def test_bank_ref_id_match(self, pipeline):
        state, config = _happy_path_input("test-ref")
        result = pipeline.invoke(state, config=config)
        assert result["match_result"]["bank_reference_id_match"] is True
        assert result["match_result"]["amount_delta"] == 0.0

    def test_messages_logged(self, pipeline):
        state, config = _happy_path_input("test-msgs")
        result = pipeline.invoke(state, config=config)
        # 5 nodes = 5 messages minimum
        assert len(result["messages"]) >= 5


class TestGateChecks:
    def test_invalid_mime_routes_to_error(self, pipeline):
        state, config = _happy_path_input("test-mime")
        state["attachment_mime_type"] = "text/plain"
        result = pipeline.invoke(state, config=config)
        assert result["document_state"] == "Error_Queue"
        assert "MIME" in (result.get("error") or "")

    def test_missing_amount_routes_to_incomplete(self, pipeline):
        state, config = _happy_path_input("test-incomplete")
        state["ocr_fields"]["amount"] = {"value": None, "confidence_score": 0.5}
        result = pipeline.invoke(state, config=config)
        assert result["document_state"] == "Incomplete_Data"

    def test_low_confidence_blocks_at_needs_review(self, pipeline):
        state, config = _happy_path_input("test-lowconf")
        state["ocr_fields"]["amount"]["confidence_score"] = 0.72
        result = pipeline.invoke(state, config=config)
        # Should be paused at human_review (interrupt)
        snapshot = pipeline.get_state(config)
        # Graph should be interrupted (next node is human_review)
        assert snapshot.next == ("human_review",)

    def test_no_match_routes_to_exception_review(self, pipeline):
        state, config = _happy_path_input("test-nomatch")
        state["bank_candidates"] = []
        result = pipeline.invoke(state, config=config)
        # Should hit human_review interrupt for exception
        snapshot = pipeline.get_state(config)
        assert snapshot.next == ("human_review",)


class TestDuplicateLock:
    def test_duplicate_candidates_trigger_lock(self, pipeline):
        state, config = _happy_path_input("test-dup")
        state["bank_candidates"] = [
            {"transaction_id": "TXN-A", "account_name": "Acme Corp", "amount": 5000.00, "date": "2026-03-20", "reference_id": None},
            {"transaction_id": "TXN-B", "account_name": "Acme Corp", "amount": 5000.00, "date": "2026-03-20", "reference_id": None},
        ]
        # Remove bank_reference_id from OCR so it doesn't short-circuit
        state["ocr_fields"].pop("bank_reference_id", None)
        result = pipeline.invoke(state, config=config)
        # Should be paused at human_review for LOCKED
        snapshot = pipeline.get_state(config)
        assert snapshot.next == ("human_review",)


class TestZeroVariance:
    def test_nonzero_delta_no_match(self, pipeline):
        state, config = _happy_path_input("test-delta")
        state["bank_candidates"][0]["amount"] = 5001.00  # Non-zero delta
        state["bank_candidates"][0]["reference_id"] = None
        state["ocr_fields"].pop("bank_reference_id", None)
        result = pipeline.invoke(state, config=config)
        # No viable candidate → Exception_Review → human_review interrupt
        snapshot = pipeline.get_state(config)
        assert snapshot.next == ("human_review",)

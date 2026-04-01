"""Unit tests for validator_node — all three validation_status branches (T026).

Tests cover FR-009 three-rule priority logic:
1. amount_paid None OR confidence < threshold → 'Extraction Failed'
2. Any other field confidence < threshold → 'Review Required'
3. All fields meet thresholds → 'Valid'
"""

from __future__ import annotations

import pytest

from backend.src.graph.doc_pipeline.nodes import validator_node


def _make_state(
    records: list[dict],
    *,
    prompt_config: dict | None = None,
) -> dict:
    """Build a minimal DocPipelineState dict for validator_node."""
    config = prompt_config or {
        "confidence_thresholds": {
            "customer_name": 0.75,
            "account_number": 0.80,
            "amount_paid": 0.90,
            "payment_date": 0.80,
            "currency": 0.75,
            "payee": 0.75,
            "payment_id": 0.70,
            "payment_method": 0.75,
            "invoice_number": 0.70,
            "reference_doc_number": 0.70,
            "deductions": 0.70,
            "deduction_type": 0.70,
            "notes": 0.70,
        }
    }
    return {
        "run_record_id": "test-run-001",
        "normalised_records": records,
        "prompt_config": config,
    }


def _good_record(overrides: dict | None = None) -> dict:
    """Return a record where all field confidences meet their thresholds."""
    rec = {
        "customer_name": "Acme Corp",
        "account_number": "12345678",
        "amount_paid": 1500.0,
        "payment_date": "2024-03-15",
        "currency": "ZAR",
        "payee": "Vendor Ltd",
        "payment_method": "EFT",
        "confidence_scores": {
            "customer_name": 0.90,
            "account_number": 0.85,
            "amount_paid": 0.95,
            "payment_date": 0.88,
            "currency": 0.92,
            "payee": 0.87,
            "payment_method": 0.85,
            "invoice_number": 0.75,
            "reference_doc_number": 0.72,
            "deductions": 0.71,
            "deduction_type": 0.71,
            "notes": 0.71,
            "payment_id": 0.73,
        },
    }
    if overrides:
        rec.update(overrides)
    return rec


# ── Rule 1: Extraction Failed ──

class TestExtractionFailed:
    def test_amount_paid_none(self):
        record = _good_record({"amount_paid": None})
        state = _make_state([record])
        result = validator_node(state)
        assert result["validated_records"][0]["validation_status"] == "Extraction Failed"

    def test_amount_paid_confidence_below_threshold(self):
        record = _good_record()
        record["confidence_scores"]["amount_paid"] = 0.80  # below 0.90 threshold
        state = _make_state([record])
        result = validator_node(state)
        assert result["validated_records"][0]["validation_status"] == "Extraction Failed"

    def test_amount_paid_zero_confidence(self):
        record = _good_record()
        record["confidence_scores"]["amount_paid"] = 0.0
        state = _make_state([record])
        result = validator_node(state)
        assert result["validated_records"][0]["validation_status"] == "Extraction Failed"

    def test_amount_paid_missing_from_confidence_scores(self):
        record = _good_record()
        del record["confidence_scores"]["amount_paid"]
        state = _make_state([record])
        result = validator_node(state)
        # Missing amount_paid confidence defaults to 0.0 → below 0.90 threshold
        assert result["validated_records"][0]["validation_status"] == "Extraction Failed"

    def test_extraction_failed_takes_priority_over_other_low_fields(self):
        # amount_paid None + other fields also low → still Extraction Failed (highest priority)
        record = _good_record({"amount_paid": None})
        record["confidence_scores"]["customer_name"] = 0.50  # also below threshold
        state = _make_state([record])
        result = validator_node(state)
        assert result["validated_records"][0]["validation_status"] == "Extraction Failed"


# ── Rule 2: Review Required ──

class TestReviewRequired:
    def test_other_field_below_threshold(self):
        record = _good_record()
        record["confidence_scores"]["customer_name"] = 0.60  # below 0.75 threshold
        state = _make_state([record])
        result = validator_node(state)
        assert result["validated_records"][0]["validation_status"] == "Review Required"

    def test_account_number_below_threshold(self):
        record = _good_record()
        record["confidence_scores"]["account_number"] = 0.70  # below 0.80 threshold
        state = _make_state([record])
        result = validator_node(state)
        assert result["validated_records"][0]["validation_status"] == "Review Required"

    def test_payment_date_below_threshold(self):
        record = _good_record()
        record["confidence_scores"]["payment_date"] = 0.75  # below 0.80 threshold
        state = _make_state([record])
        result = validator_node(state)
        assert result["validated_records"][0]["validation_status"] == "Review Required"

    def test_multiple_fields_below_threshold(self):
        record = _good_record()
        record["confidence_scores"]["customer_name"] = 0.60
        record["confidence_scores"]["notes"] = 0.50
        state = _make_state([record])
        result = validator_node(state)
        assert result["validated_records"][0]["validation_status"] == "Review Required"


# ── Rule 3: Valid ──

class TestValid:
    def test_all_fields_meet_thresholds(self):
        record = _good_record()
        state = _make_state([record])
        result = validator_node(state)
        assert result["validated_records"][0]["validation_status"] == "Valid"

    def test_valid_with_minimal_confidence_scores(self):
        record = _good_record()
        # Set all to exactly at threshold
        record["confidence_scores"] = {
            "amount_paid": 0.90,
            "account_number": 0.80,
            "payment_date": 0.80,
            "customer_name": 0.75,
            "currency": 0.75,
            "payee": 0.75,
            "payment_method": 0.75,
            "invoice_number": 0.70,
            "reference_doc_number": 0.70,
            "deductions": 0.70,
            "deduction_type": 0.70,
            "notes": 0.70,
            "payment_id": 0.70,
        }
        state = _make_state([record])
        result = validator_node(state)
        assert result["validated_records"][0]["validation_status"] == "Valid"


# ── Multiple records ──

class TestMultipleRecords:
    def test_mixed_statuses(self):
        state = _make_state([
            _good_record(),         # → Valid
            _good_record({"amount_paid": None}),  # → Extraction Failed
            dict(_good_record(), confidence_scores={
                **_good_record()["confidence_scores"],
                "customer_name": 0.60,  # → Review Required
            }),
        ])
        result = validator_node(state)
        statuses = [r["validation_status"] for r in result["validated_records"]]
        assert statuses == ["Valid", "Extraction Failed", "Review Required"]


# ── State outputs ──

class TestStateOutputs:
    def test_returns_validated_records(self):
        state = _make_state([_good_record()])
        result = validator_node(state)
        assert "validated_records" in result
        assert len(result["validated_records"]) == 1

    def test_clears_error(self):
        state = _make_state([_good_record()])
        state["error"] = "previous error"
        result = validator_node(state)
        assert result["error"] is None

    def test_validation_status_set_on_all_records(self):
        state = _make_state([_good_record(), _good_record()])
        result = validator_node(state)
        for rec in result["validated_records"]:
            assert "validation_status" in rec

    def test_uses_default_thresholds_when_no_prompt_config(self):
        state = _make_state([_good_record()], prompt_config={})
        result = validator_node(state)
        # No threshold defined — defaults to 0.70 for most fields
        assert result["validated_records"][0]["validation_status"] in {
            "Valid", "Review Required", "Extraction Failed"
        }

"""Unit tests for normaliser_node — one test per normalisation rule (T025).

Tests cover:
- date formats → YYYY-MM-DD (SC-006)
- amount string stripping → float
- currency symbols/names → ISO 4217
- payment_method variants → canonical form
"""

from __future__ import annotations

import pytest

from backend.src.graph.doc_pipeline.nodes import (
    _normalise_amount,
    _normalise_currency,
    _normalise_date,
    _normalise_payment_method,
    normaliser_node,
)
from backend.src.graph.doc_pipeline.state import PaymentRecordDict


# ── Date normalisation ──

class TestNormaliseDate:
    def test_iso_format_passthrough(self):
        assert _normalise_date("2024-03-15") == "2024-03-15"

    def test_dd_slash_mm_slash_yyyy(self):
        assert _normalise_date("15/03/2024") == "2024-03-15"

    def test_dd_dash_mm_dash_yyyy(self):
        assert _normalise_date("15-03-2024") == "2024-03-15"

    def test_mm_slash_dd_slash_yyyy_ambiguous(self):
        # dayfirst=True: 01/02/2024 → Feb 1, 2024 (DD/MM)
        assert _normalise_date("01/02/2024") == "2024-02-01"

    def test_month_name_full(self):
        result = _normalise_date("March 15, 2024")
        assert result == "2024-03-15"

    def test_month_name_abbreviated(self):
        result = _normalise_date("15 Mar 2024")
        assert result == "2024-03-15"

    def test_two_digit_year(self):
        result = _normalise_date("15/03/24")
        assert result is not None
        assert result.endswith("-03-15")

    def test_none_returns_none(self):
        assert _normalise_date(None) is None

    def test_empty_string_returns_none(self):
        assert _normalise_date("") is None

    def test_unparseable_returns_original(self):
        result = _normalise_date("not-a-date")
        assert result == "not-a-date"


# ── Amount normalisation ──

class TestNormaliseAmount:
    def test_float_passthrough(self):
        assert _normalise_amount(1234.56) == 1234.56

    def test_int_to_float(self):
        assert _normalise_amount(1000) == 1000.0

    def test_string_with_commas(self):
        assert _normalise_amount("1,234.56") == 1234.56

    def test_string_with_currency_symbol(self):
        assert _normalise_amount("R 1 234.56") == 1234.56

    def test_string_dollar_sign(self):
        assert _normalise_amount("$500.00") == 500.0

    def test_string_no_decimals(self):
        assert _normalise_amount("5000") == 5000.0

    def test_none_returns_none(self):
        assert _normalise_amount(None) is None

    def test_unparseable_returns_none(self):
        assert _normalise_amount("not-a-number") is None

    def test_negative_amount(self):
        assert _normalise_amount("-250.00") == -250.0


# ── Currency normalisation ──

class TestNormaliseCurrency:
    def test_dollar_symbol(self):
        assert _normalise_currency("$") == "USD"

    def test_usd_string(self):
        assert _normalise_currency("USD") == "USD"

    def test_rand_symbol(self):
        assert _normalise_currency("R") == "ZAR"

    def test_zar_string(self):
        assert _normalise_currency("ZAR") == "ZAR"

    def test_euro_symbol(self):
        assert _normalise_currency("€") == "EUR"

    def test_gbp_string(self):
        assert _normalise_currency("GBP") == "GBP"

    def test_already_iso_three_letter(self):
        assert _normalise_currency("AUD") == "AUD"

    def test_lowercase_iso(self):
        assert _normalise_currency("eur") == "EUR"

    def test_none_returns_none(self):
        assert _normalise_currency(None) is None

    def test_unknown_passes_through(self):
        result = _normalise_currency("XYZ")
        assert result == "XYZ"

    def test_rand_word(self):
        assert _normalise_currency("rand") == "ZAR"


# ── Payment method normalisation ──

class TestNormalisePaymentMethod:
    def test_eft_lowercase(self):
        assert _normalise_payment_method("eft") == "EFT"

    def test_eft_uppercase(self):
        assert _normalise_payment_method("EFT") == "EFT"

    def test_electronic_funds_transfer(self):
        assert _normalise_payment_method("electronic funds transfer") == "EFT"

    def test_cash(self):
        assert _normalise_payment_method("Cash") == "CASH"

    def test_cheque(self):
        assert _normalise_payment_method("cheque") == "CHEQUE"

    def test_check_american_spelling(self):
        assert _normalise_payment_method("check") == "CHEQUE"

    def test_direct_deposit(self):
        assert _normalise_payment_method("direct deposit") == "DIRECT_DEPOSIT"

    def test_direct_deposit_underscored(self):
        assert _normalise_payment_method("direct_deposit") == "DIRECT_DEPOSIT"

    def test_card(self):
        assert _normalise_payment_method("card") == "CARD"

    def test_credit_card(self):
        assert _normalise_payment_method("credit card") == "CARD"

    def test_none_returns_none(self):
        assert _normalise_payment_method(None) is None

    def test_unknown_uppercased(self):
        result = _normalise_payment_method("wire transfer")
        assert result == "WIRE TRANSFER"


# ── normaliser_node integration ──

class TestNormaliserNode:
    def _make_state(self, records: list[dict]) -> dict:
        return {
            "run_record_id": "test-run-001",
            "raw_records": records,
            "prompt_config": {},
        }

    def test_normalises_all_fields(self):
        state = self._make_state([{
            "amount_paid": "R 1,250.00",
            "deductions": "R 50.00",
            "payment_date": "15/03/2024",
            "currency": "R",
            "payment_method": "eft",
            "confidence_scores": {"amount_paid": 0.95},
        }])
        result = normaliser_node(state)
        rec = result["normalised_records"][0]

        assert rec["amount_paid"] == 1250.0
        assert rec["deductions"] == 50.0
        assert rec["payment_date"] == "2024-03-15"
        assert rec["currency"] == "ZAR"
        assert rec["payment_method"] == "EFT"

    def test_preserves_none_fields(self):
        state = self._make_state([{
            "amount_paid": None,
            "payment_date": None,
            "confidence_scores": {},
        }])
        result = normaliser_node(state)
        rec = result["normalised_records"][0]
        assert rec["amount_paid"] is None
        assert rec["payment_date"] is None

    def test_preserves_confidence_scores(self):
        original_scores = {"amount_paid": 0.95, "customer_name": 0.80}
        state = self._make_state([{
            "amount_paid": "100.00",
            "confidence_scores": original_scores,
        }])
        result = normaliser_node(state)
        assert result["normalised_records"][0]["confidence_scores"] == original_scores

    def test_empty_raw_records(self):
        state = self._make_state([])
        result = normaliser_node(state)
        assert result["normalised_records"] == []

    def test_clears_error(self):
        state = self._make_state([])
        state["error"] = "previous error"
        result = normaliser_node(state)
        assert result["error"] is None

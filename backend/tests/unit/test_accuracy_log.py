"""Unit tests for accuracy.jsonl AccuracyLogEntry format (T040).

Asserts all 10 required fields are present and correctly typed in the
accuracy log entry written by excel_writer_node.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

# Required field names and their expected Python types
_REQUIRED_FIELDS: dict[str, type | tuple[type, ...]] = {
    "timestamp": str,
    "source_filename": str,
    "doc_type": str,
    "validation_status": str,
    "overall_confidence": float,
    "fields_extracted": int,
    "null_fields": int,
    "extraction_attempts": int,
    "llm_provider": str,
    "llm_model": str,
}


def _make_state(tmp_path: Path, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a minimal DocPipelineState for excel_writer_node."""
    validated_records = [
        {
            "customer_name": "Test Corp",
            "account_number": "****1234",
            "payee": "Payee Ltd",
            "payment_id": "TXN-1",
            "payment_method": "EFT",
            "payment_date": "2024-03-15",
            "invoice_number": "INV-100",
            "reference_doc_number": None,
            "amount_paid": 1000.0,
            "currency": "ZAR",
            "deductions": None,
            "deduction_type": None,
            "notes": None,
            "page_number": 1,
            "confidence_scores": {
                "customer_name": 0.90, "account_number": 0.85,
                "payee": 0.87, "payment_id": 0.75, "payment_method": 0.88,
                "payment_date": 0.92, "invoice_number": 0.80,
                "reference_doc_number": 0.70, "amount_paid": 0.95,
                "currency": 0.93, "deductions": 0.70, "deduction_type": 0.70,
                "notes": 0.70,
            },
            "validation_status": "Valid",
        }
    ]

    base: dict[str, Any] = {
        "batch_id": str(uuid.uuid4()),
        "run_record_id": str(uuid.uuid4()),
        "source_file_path": "/src/invoice.pdf",
        "work_file_path": "/work/abc_invoice.pdf",
        "guid_filename": "abc_invoice.pdf",
        "doc_type": "remittance",
        "prompt_config": {
            "context_hint": "Test",
            "field_hints": {},
            "confidence_thresholds": {"amount_paid": 0.90},
            "required_fields": ["amount_paid"],
        },
        "validated_records": validated_records,
        "normalised_records": validated_records,
        "raw_records": validated_records,
        "extraction_attempts": 1,
        "error": None,
        "error_type": None,
    }
    if extra:
        base.update(extra)
    return base


class TestAccuracyLogEntry:
    """Assert all 10 AccuracyLogEntry fields are written to accuracy.jsonl."""

    def _run_excel_writer(self, state: dict, tmp_path: Path, monkeypatch) -> dict:
        """Invoke excel_writer_node with DB and file I/O stubbed out."""
        settings_mock = MagicMock(
            provider="openai",
            model="gpt-4o",
            output_directory=str(tmp_path),
        )

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker, Session
        from src.db.base import Base

        engine = create_engine(
            f"sqlite:///{tmp_path}/test_acc.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine)
        test_session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

        with (
            patch("src.graph.doc_pipeline.nodes.load_settings", return_value=settings_mock),
            patch("src.graph.doc_pipeline.nodes.SessionLocal", test_session_factory),
            patch("src.graph.doc_pipeline.nodes._rewrite_results_xlsx"),
            patch("src.audit.logger.log_entry"),
        ):
            from src.graph.doc_pipeline.nodes import excel_writer_node
            # Add required DB rows
            from src.db.models import BatchRunModel, RunRecordModel
            now = datetime.now(timezone.utc)
            with test_session_factory() as session:
                session.add(BatchRunModel(
                    batch_id=state["batch_id"],
                    triggered_at=now,
                    total_files=1,
                    total_records=0,
                    status="In Progress",
                ))
                session.add(RunRecordModel(
                    record_id=state["run_record_id"],
                    batch_id=state["batch_id"],
                    source_filename="invoice.pdf",
                    work_path=state["work_file_path"],
                    guid_filename=state["guid_filename"],
                    started_at=now,
                    record_count=0,
                    status="Processing",
                ))
                session.commit()

            return excel_writer_node(state)

    def test_all_10_fields_present(self, tmp_path, monkeypatch):
        """All 10 required AccuracyLogEntry fields must be in accuracy.jsonl."""
        state = _make_state(tmp_path)
        self._run_excel_writer(state, tmp_path, monkeypatch)

        jsonl_path = tmp_path / "accuracy.jsonl"
        assert jsonl_path.exists(), "accuracy.jsonl was not created"

        with open(jsonl_path, encoding="utf-8") as f:
            entry = json.loads(f.readline())

        for field in _REQUIRED_FIELDS:
            assert field in entry, f"Missing field: {field}"

    def test_field_types_are_correct(self, tmp_path, monkeypatch):
        """Each AccuracyLogEntry field must have the expected Python type."""
        state = _make_state(tmp_path)
        self._run_excel_writer(state, tmp_path, monkeypatch)

        jsonl_path = tmp_path / "accuracy.jsonl"
        with open(jsonl_path, encoding="utf-8") as f:
            entry = json.loads(f.readline())

        for field, expected_type in _REQUIRED_FIELDS.items():
            assert isinstance(entry[field], expected_type), (
                f"Field '{field}': expected {expected_type}, got {type(entry[field])}"
            )

    def test_llm_provider_reflects_settings(self, tmp_path, monkeypatch):
        """llm_provider in accuracy.jsonl should match the configured LLM provider."""
        state = _make_state(tmp_path)
        self._run_excel_writer(state, tmp_path, monkeypatch)

        with open(tmp_path / "accuracy.jsonl", encoding="utf-8") as f:
            entry = json.loads(f.readline())

        assert entry["llm_provider"] == "openai"
        assert entry["llm_model"] == "gpt-4o"

    def test_accuracy_log_appends_multiple_entries(self, tmp_path, monkeypatch):
        """Each excel_writer_node call should append a new line to accuracy.jsonl."""
        state1 = _make_state(tmp_path)
        state2 = _make_state(tmp_path)  # new batch_id / run_record_id

        self._run_excel_writer(state1, tmp_path, monkeypatch)

        # Clear DB and re-create for second run
        jsonl_path = tmp_path / "accuracy.jsonl"
        state2_fresh = _make_state(tmp_path)
        state2_fresh["doc_type"] = "email"
        self._run_excel_writer(state2_fresh, tmp_path, monkeypatch)

        with open(jsonl_path, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]

        assert len(lines) >= 2, "accuracy.jsonl should have at least 2 appended entries"

    def test_overall_confidence_is_float_between_0_and_1(self, tmp_path, monkeypatch):
        """overall_confidence must be a float in [0, 1]."""
        state = _make_state(tmp_path)
        self._run_excel_writer(state, tmp_path, monkeypatch)

        with open(tmp_path / "accuracy.jsonl", encoding="utf-8") as f:
            entry = json.loads(f.readline())

        conf = entry["overall_confidence"]
        assert isinstance(conf, float)
        assert 0.0 <= conf <= 1.0

    def test_extraction_attempts_equals_state_value(self, tmp_path, monkeypatch):
        """extraction_attempts in log must equal the value from state."""
        state = _make_state(tmp_path, {"extraction_attempts": 2})
        self._run_excel_writer(state, tmp_path, monkeypatch)

        with open(tmp_path / "accuracy.jsonl", encoding="utf-8") as f:
            entry = json.loads(f.readline())

        assert entry["extraction_attempts"] == 2

"""Integration test — full DocPipeline graph invocation with stub LLMAdapter (T027).

Tests:
- Full DocPipeline invocation with canned LLM responses
- PaymentRecord DB rows created after successful run
- RunRecord.status = 'Completed' after successful run
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── Only run if SQLAlchemy/DB is available (sets DATABASE_URL to SQLite for tests) ──
pytest.importorskip("sqlalchemy")


@pytest.fixture(autouse=True)
def use_sqlite_db(tmp_path, monkeypatch):
    """Override DATABASE_URL to use an isolated SQLite in-memory DB for tests."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("DATABASE_URL", db_url)

    # Re-create engine and tables for this test
    from sqlalchemy import create_engine
    from src.db.base import Base

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    from src.db import engine as engine_module
    from sqlalchemy.orm import sessionmaker, Session

    # Patch the engine and SessionLocal used by the production code
    monkeypatch.setattr(engine_module, "engine", engine)
    monkeypatch.setattr(
        engine_module,
        "SessionLocal",
        sessionmaker(bind=engine, class_=Session, expire_on_commit=False),
    )

    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def setup_db_records(use_sqlite_db, tmp_path):
    """Create BatchRun + RunRecord rows so the graph nodes can update them."""
    from src.db.engine import SessionLocal
    from src.db.models import BatchRunModel, RunRecordModel

    batch_id = str(uuid.uuid4())
    run_record_id = str(uuid.uuid4())
    guid_filename = f"{uuid.uuid4().hex}_test.pdf"
    work_path = str(tmp_path / guid_filename)
    source_filename = "test.pdf"

    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        session.add(BatchRunModel(
            batch_id=batch_id,
            triggered_at=now,
            total_files=1,
            total_records=0,
            status="In Progress",
        ))
        session.add(RunRecordModel(
            record_id=run_record_id,
            batch_id=batch_id,
            source_filename=source_filename,
            work_path=work_path,
            guid_filename=guid_filename,
            started_at=now,
            record_count=0,
            status="Processing",
        ))
        session.commit()

    return {
        "batch_id": batch_id,
        "run_record_id": run_record_id,
        "work_path": work_path,
        "source_filename": source_filename,
    }


def _make_canned_llm_responses(batch_id: str) -> tuple[str, str]:
    """Return (classify_response, extract_response) for a canned pipeline run."""
    classify = "remittance"
    extract = json.dumps([{
        "customer_name": "Test Corp",
        "account_number": "11111111",
        "payee": "Payee Ltd",
        "payment_id": "TXN-999",
        "payment_method": "EFT",
        "payment_date": "15/03/2024",
        "invoice_number": "INV-500",
        "reference_doc_number": None,
        "amount_paid": 2500.0,
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
    }])
    return classify, extract


def _make_fake_fitz_doc(num_pages: int = 1) -> MagicMock:
    """Return a fitz.Document mock with num_pages pages."""
    pix = MagicMock()
    pix.samples = b"\x00" * 100
    pix.tobytes.return_value = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20

    page = MagicMock()
    page.get_pixmap.return_value = pix

    doc = MagicMock()
    doc.__getitem__ = MagicMock(return_value=page)
    doc.__iter__ = MagicMock(return_value=iter([page] * num_pages))
    doc.close = MagicMock()
    return doc


@pytest.fixture
def fake_pdf_file(tmp_path) -> Path:
    """Create a minimal fake PDF placeholder in tmp_path."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake content")
    return pdf_path


class TestDocPipelineIntegration:
    """Full DocPipeline graph invocation with stubbed LLM — no real LLM calls."""

    def test_successful_run_creates_payment_record(self, setup_db_records, fake_pdf_file, tmp_path, monkeypatch):
        """PaymentRecord DB row should be created after a successful graph run."""
        from src.db.engine import SessionLocal
        from src.db.models import PaymentRecordModel
        from src.graph.doc_pipeline.pipeline import build_doc_pipeline

        run_data = setup_db_records
        # Point work_file_path at the fake PDF
        work_file_path = str(fake_pdf_file)

        classify_response, extract_response = _make_canned_llm_responses(run_data["batch_id"])
        fake_doc = _make_fake_fitz_doc(1)

        # Patch output directory to tmp_path
        monkeypatch.setattr(
            "src.settings_store.load_settings",
            lambda: MagicMock(
                provider="stub",
                model="stub-model",
                output_directory=str(tmp_path),
                **{k: "" for k in ["api_key", "base_url", "source_directory", "work_directory", "review_directory"]},
                temperature=0.0,
            ),
        )

        initial_state = {
            "batch_id": run_data["batch_id"],
            "run_record_id": run_data["run_record_id"],
            "source_file_path": str(fake_pdf_file),
            "work_file_path": work_file_path,
            "guid_filename": run_data["work_path"].split("/")[-1],
            "extraction_attempts": 0,
            "error": None,
            "error_type": None,
        }

        with (
            patch("src.graph.doc_pipeline.nodes.fitz.open", return_value=fake_doc),
            patch("src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
            patch("src.graph.doc_pipeline.nodes._load_prompt_config", return_value={
                "context_hint": "Test",
                "field_hints": {},
                "confidence_thresholds": {"amount_paid": 0.90},
                "required_fields": ["amount_paid"],
            }),
        ):
            mock_adapter = mock_adapter_cls.return_value
            # First call = classifier, subsequent = extractor
            mock_adapter.invoke_vision.side_effect = [classify_response, extract_response]

            graph = build_doc_pipeline()
            final_state = graph.invoke(initial_state)

        assert final_state.get("error") is None

        with SessionLocal() as session:
            records = (
                session.query(PaymentRecordModel)
                .filter(PaymentRecordModel.run_record_id == run_data["run_record_id"])
                .all()
            )
        assert len(records) == 1
        assert records[0].amount_paid == 2500.0

    def test_successful_run_sets_run_record_completed(self, setup_db_records, fake_pdf_file, tmp_path, monkeypatch):
        """RunRecord.status should be 'Completed' after a successful graph run."""
        from src.db.engine import SessionLocal
        from src.db.models import RunRecordModel
        from src.graph.doc_pipeline.pipeline import build_doc_pipeline

        run_data = setup_db_records
        classify_response, extract_response = _make_canned_llm_responses(run_data["batch_id"])
        fake_doc = _make_fake_fitz_doc(1)

        monkeypatch.setattr(
            "src.settings_store.load_settings",
            lambda: MagicMock(
                provider="stub",
                model="stub-model",
                output_directory=str(tmp_path),
                **{k: "" for k in ["api_key", "base_url", "source_directory", "work_directory", "review_directory"]},
                temperature=0.0,
            ),
        )

        initial_state = {
            "batch_id": run_data["batch_id"],
            "run_record_id": run_data["run_record_id"],
            "source_file_path": str(fake_pdf_file),
            "work_file_path": str(fake_pdf_file),
            "guid_filename": "guid_test.pdf",
            "extraction_attempts": 0,
            "error": None,
            "error_type": None,
        }

        with (
            patch("src.graph.doc_pipeline.nodes.fitz.open", return_value=fake_doc),
            patch("src.graph.doc_pipeline.nodes.LLMAdapter") as mock_adapter_cls,
            patch("src.graph.doc_pipeline.nodes._load_prompt_config", return_value={
                "context_hint": "Test",
                "field_hints": {},
                "confidence_thresholds": {"amount_paid": 0.90},
                "required_fields": ["amount_paid"],
            }),
        ):
            mock_adapter = mock_adapter_cls.return_value
            mock_adapter.invoke_vision.side_effect = [classify_response, extract_response]

            graph = build_doc_pipeline()
            graph.invoke(initial_state)

        with SessionLocal() as session:
            run_rec = session.get(RunRecordModel, run_data["run_record_id"])

        assert run_rec is not None
        assert run_rec.status == "Completed"
        assert run_rec.record_count == 1

    def test_failed_classification_sets_run_record_failed(self, setup_db_records, fake_pdf_file, tmp_path, monkeypatch):
        """On classifier_node failure, RunRecord.status should be 'Failed'."""
        from src.db.engine import SessionLocal
        from src.db.models import RunRecordModel
        from src.graph.doc_pipeline.pipeline import build_doc_pipeline

        run_data = setup_db_records

        monkeypatch.setattr(
            "src.settings_store.load_settings",
            lambda: MagicMock(
                provider="stub",
                model="stub-model",
                output_directory=str(tmp_path),
                **{k: "" for k in ["api_key", "base_url", "source_directory", "work_directory", "review_directory"]},
                temperature=0.0,
            ),
        )

        initial_state = {
            "batch_id": run_data["batch_id"],
            "run_record_id": run_data["run_record_id"],
            "source_file_path": str(fake_pdf_file),
            "work_file_path": str(fake_pdf_file),
            "guid_filename": "guid_test.pdf",
            "extraction_attempts": 0,
            "error": None,
            "error_type": None,
        }

        with (
            patch("src.graph.doc_pipeline.nodes.fitz.open") as mock_open,
        ):
            mock_open.side_effect = RuntimeError("Cannot open file")

            graph = build_doc_pipeline()
            final_state = graph.invoke(initial_state)

        assert final_state.get("error") is not None

        with SessionLocal() as session:
            run_rec = session.get(RunRecordModel, run_data["run_record_id"])

        assert run_rec.status == "Failed"

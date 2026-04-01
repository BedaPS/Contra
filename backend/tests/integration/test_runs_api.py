"""Integration test — Runs API endpoints (T038).

Covers:
- POST /api/v1/runs → 202 RunStartedResponse
- POST /api/v1/runs → 409 when a run with status='In Progress' already exists
- GET /api/v1/runs → 200 list
- GET /api/v1/runs/{batch_id} → 200 detail + 404 missing
- GET /api/v1/results → 200 filtered list
- GET /api/v1/runs/{batch_id}/stream → SSE events
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Bootstrap TestClient against an isolated SQLite DB ───────────────────

@pytest.fixture(autouse=True, scope="module")
def isolate_sqlite():
    """Override DATABASE_URL to SQLite so no MSSQL is needed."""
    import os

    # Must be set before importing src modules
    os.environ.setdefault("DATABASE_URL", "sqlite:///./test_runs_api.db")


@pytest.fixture(scope="module")
def test_client(tmp_path_factory):
    """Build a fresh app with SQLite in-memory tables."""
    import os

    db_path = tmp_path_factory.mktemp("db") / "runs_api_test.db"
    db_url = f"sqlite:///{db_path}"

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker, Session

    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    from src.db.base import Base

    Base.metadata.create_all(engine)
    test_session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    # Patch at src.db.engine level (where routes.py imports from)
    with (
        patch("src.db.engine.engine", engine),
        patch("src.db.engine.SessionLocal", test_session_factory),
        patch("src.api.routes.SessionLocal", test_session_factory),
    ):
        from src.api.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, test_session_factory

    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(test_client):
    return test_client[0]


@pytest.fixture()
def session_factory(test_client):
    return test_client[1]


def _insert_batch_run(session_factory, status: str = "Completed") -> str:
    """Insert a BatchRunModel row and return its batch_id."""
    from src.db.models import BatchRunModel

    batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        session.add(BatchRunModel(
            batch_id=batch_id,
            triggered_at=now,
            total_files=2,
            total_records=3,
            status=status,
        ))
        session.commit()
    return batch_id


def _insert_run_record(session_factory, batch_id: str) -> str:
    """Insert a RunRecordModel row linked to batch_id, return record_id."""
    from src.db.models import RunRecordModel

    record_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        session.add(RunRecordModel(
            record_id=record_id,
            batch_id=batch_id,
            source_filename="invoice.pdf",
            work_path="/work/invoice.pdf",
            guid_filename="abc_invoice.pdf",
            started_at=now,
            record_count=1,
            status="Completed",
        ))
        session.commit()
    return record_id


def _insert_payment_record(session_factory, batch_id: str, run_record_id: str) -> str:
    """Insert a PaymentRecordModel row, return id."""
    from src.db.models import PaymentRecordModel

    now = datetime.now(timezone.utc)
    with session_factory() as session:
        rec = PaymentRecordModel(
            run_record_id=run_record_id,
            batch_id=batch_id,
            source_filename="invoice.pdf",
            doc_type="remittance",
            page_number=1,
            customer_name="Corp A",
            account_number="****1234",
            payee=None,
            payment_id="TXN-1",
            payment_method="EFT",
            payment_date="2024-03-15",
            invoice_number="INV-100",
            reference_doc_number=None,
            amount_paid=1000.0,
            currency="ZAR",
            deductions=None,
            deduction_type=None,
            notes=None,
            validation_status="Valid",
            overall_confidence=0.92,
            confidence_scores='{"amount_paid": 0.92}',
            created_at=now,
        )
        session.add(rec)
        session.commit()
        return str(rec.id)


# ── POST /api/v1/runs ─────────────────────────────────────────────────────

class TestPostRuns:
    def test_returns_202_with_batch_id(self, client, tmp_path):
        """POST /runs should return 202 with batch_id when settings are valid."""
        with (
            patch("src.api.routes.load_settings") as mock_settings,
            patch("src.api.routes.run_service.create_batch_run") as mock_create,
            patch("src.api.routes.asyncio.create_task"),
        ):
            mock_settings.return_value = MagicMock(
                source_directory=str(tmp_path / "source"),
                work_directory=str(tmp_path / "work"),
            )
            batch_id = str(uuid.uuid4())
            mock_create.return_value = {
                "batch_id": batch_id,
                "total_files": 3,
                "status": "In Progress",
            }

            # Patch SessionLocal for the 409 check to return no in-progress batch
            with patch("src.api.routes.SessionLocal") as mock_sl:
                mock_session = MagicMock()
                mock_session.__enter__ = MagicMock(return_value=mock_session)
                mock_session.__exit__ = MagicMock(return_value=False)
                mock_session.query.return_value.filter.return_value.first.return_value = None
                mock_sl.return_value = mock_session

                response = client.post("/api/v1/runs")

        assert response.status_code == 202
        body = response.json()
        assert body["batch_id"] == batch_id
        assert body["total_files"] == 3
        assert body["status"] == "In Progress"

    def test_returns_409_when_in_progress_batch_exists(self, client, session_factory):
        """POST /runs must return 409 when a BatchRun with status='In Progress' exists."""
        # Insert a live In Progress batch into the test DB
        existing_batch_id = _insert_batch_run(session_factory, status="In Progress")

        with patch("src.api.routes.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                source_directory="/some/source",
                work_directory="/some/work",
            )
            response = client.post("/api/v1/runs")

        assert response.status_code == 409
        assert "In Progress" in response.json()["detail"]

        # clean up
        from src.db.models import BatchRunModel
        with session_factory() as session:
            session.query(BatchRunModel).filter(
                BatchRunModel.batch_id == existing_batch_id
            ).delete()
            session.commit()

    def test_returns_400_when_source_directory_not_configured(self, client):
        """POST /runs returns 400 if source_directory is not set."""
        with patch("src.api.routes.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                source_directory="",
                work_directory="/some/work",
            )
            response = client.post("/api/v1/runs")

        assert response.status_code == 400

    def test_returns_400_when_create_batch_run_raises_file_not_found(self, client, session_factory):
        """POST /runs returns 400 if create_batch_run raises FileNotFoundError."""
        with (
            patch("src.api.routes.load_settings") as mock_settings,
            patch("src.api.routes.run_service.create_batch_run") as mock_create,
        ):
            mock_settings.return_value = MagicMock(
                source_directory="/valid/source",
                work_directory="/valid/work",
            )
            mock_create.side_effect = FileNotFoundError("source_directory not found")

            with patch("src.api.routes.SessionLocal") as mock_sl:
                mock_session = MagicMock()
                mock_session.__enter__ = MagicMock(return_value=mock_session)
                mock_session.__exit__ = MagicMock(return_value=False)
                mock_session.query.return_value.filter.return_value.first.return_value = None
                mock_sl.return_value = mock_session

                response = client.post("/api/v1/runs")

        assert response.status_code == 400


# ── GET /api/v1/runs ───────────────────────────────────────────────────────

class TestGetRuns:
    def test_returns_200_empty_list(self, client):
        """GET /runs → 200 even when no BatchRun rows exist."""
        response = client.get("/api/v1/runs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_returns_list_of_batch_runs(self, client, session_factory):
        """GET /runs should include the batch runs we created."""
        b1 = _insert_batch_run(session_factory, status="Completed")
        b2 = _insert_batch_run(session_factory, status="Completed")

        response = client.get("/api/v1/runs")

        assert response.status_code == 200
        ids = [r["batch_id"] for r in response.json()]
        assert b1 in ids
        assert b2 in ids


# ── GET /api/v1/runs/{batch_id} ────────────────────────────────────────────

class TestGetRunDetail:
    def test_returns_404_for_unknown_batch(self, client):
        """GET /runs/{batch_id} returns 404 for a non-existent batch_id."""
        response = client.get(f"/api/v1/runs/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_returns_batch_detail_with_run_records(self, client, session_factory):
        """GET /runs/{batch_id} returns BatchRunDetail including run_records."""
        batch_id = _insert_batch_run(session_factory)
        run_record_id = _insert_run_record(session_factory, batch_id)

        response = client.get(f"/api/v1/runs/{batch_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["batch_id"] == batch_id
        assert len(body["run_records"]) == 1
        assert body["run_records"][0]["record_id"] == run_record_id


# ── GET /api/v1/results ────────────────────────────────────────────────────

class TestGetResults:
    def test_returns_200_empty_list(self, client):
        """GET /results returns 200 with empty list when no records exist."""
        response = client.get("/api/v1/results")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_filters_by_batch_id(self, client, session_factory):
        """GET /results?batch_id=... should return only records for that batch."""
        b1 = _insert_batch_run(session_factory)
        r1 = _insert_run_record(session_factory, b1)
        _insert_payment_record(session_factory, b1, r1)

        b2 = _insert_batch_run(session_factory)
        r2 = _insert_run_record(session_factory, b2)
        _insert_payment_record(session_factory, b2, r2)

        response = client.get(f"/api/v1/results?batch_id={b1}")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["batch_id"] == b1

    def test_filters_by_validation_status(self, client, session_factory):
        """GET /results?validation_status=Valid should only return Valid records."""
        batch_id = _insert_batch_run(session_factory)
        run_record_id = _insert_run_record(session_factory, batch_id)
        _insert_payment_record(session_factory, batch_id, run_record_id)

        response = client.get("/api/v1/results?validation_status=Valid")
        assert response.status_code == 200
        for rec in response.json():
            assert rec["validation_status"] == "Valid"

    def test_filters_by_doc_type(self, client, session_factory):
        """GET /results?doc_type=remittance should only return remittance records."""
        batch_id = _insert_batch_run(session_factory)
        run_record_id = _insert_run_record(session_factory, batch_id)
        _insert_payment_record(session_factory, batch_id, run_record_id)

        response = client.get("/api/v1/results?doc_type=remittance")
        assert response.status_code == 200
        for rec in response.json():
            assert rec["doc_type"] == "remittance"

    def test_pagination_skip_and_limit(self, client, session_factory):
        """GET /results?skip=1&limit=1 should respect pagination parameters."""
        batch_id = _insert_batch_run(session_factory)
        run_record_id = _insert_run_record(session_factory, batch_id)
        # Insert 2 records for the same batch
        _insert_payment_record(session_factory, batch_id, run_record_id)
        _insert_payment_record(session_factory, batch_id, run_record_id)

        response = client.get(f"/api/v1/results?batch_id={batch_id}&skip=0&limit=1")
        assert response.status_code == 200
        assert len(response.json()) == 1


# ── GET /api/v1/runs/{batch_id}/stream ────────────────────────────────────

class TestStreamEndpoint:
    def test_returns_404_for_unknown_batch_id(self, client):
        """Stream endpoint returns 404 when batch_id does not exist in DB."""
        response = client.get(f"/api/v1/runs/{uuid.uuid4()}/stream")
        assert response.status_code == 404

    def test_streams_events_from_queue(self, client, session_factory):
        """Stream endpoint yields 'data:' prefixed SSE lines from the batch queue."""
        import asyncio, json as json_module
        from src.services import run_service as rs

        batch_id = _insert_batch_run(session_factory, status="In Progress")

        # Seed the queue with 2 events: a file event and BATCH_COMPLETED
        q = asyncio.Queue()
        q.put_nowait({"event": "FILE_COMPLETED", "batch_id": batch_id, "filename": "x.pdf"})
        q.put_nowait({"event": "BATCH_COMPLETED", "batch_id": batch_id})

        with patch.object(rs, "_get_queue", return_value=q):
            with patch.object(rs, "remove_queue"):
                response = client.get(f"/api/v1/runs/{batch_id}/stream")

        assert response.status_code == 200
        lines = [l for l in response.text.split("\n") if l.startswith("data:")]
        assert len(lines) == 2

        first_event = json_module.loads(lines[0][len("data: "):])
        assert first_event["event"] == "FILE_COMPLETED"

        last_event = json_module.loads(lines[1][len("data: "):])
        assert last_event["event"] == "BATCH_COMPLETED"

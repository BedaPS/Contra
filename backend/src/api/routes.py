"""API routes — thin layer, business logic lives in agents & state_machine."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from src.audit import logger as audit_log
from src.db.engine import SessionLocal
from src.db.models import BatchRunModel, PaymentRecordModel, RunRecordModel
from src.graph.pipeline import get_topology
from src.schemas.llm_settings import LLMSettings, LLMSettingsResponse
from src.schemas.parsed_document import ParsedDocument
from src.schemas.payment_record import PaymentRecordResponse
from src.schemas.run import BatchRunDetail, BatchRunSummary, RunRecordSummary, RunStartedResponse
from src.services import run_service
from src.settings_store import clear_cache, load_settings, save_settings

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/pipeline/topology")
async def pipeline_topology() -> dict:
    """Return the current pipeline graph topology for dynamic UI rendering."""
    return get_topology()


@router.get("/audit")
async def get_audit_log() -> list[dict]:
    """Return all audit entries (read-only view)."""
    return [e.model_dump() for e in audit_log.entries()]


# ── LLM Settings ──────────────────────────────────────────────────────────


@router.get("/settings/llm", response_model=LLMSettingsResponse)
async def get_llm_settings() -> LLMSettingsResponse:
    """Return current LLM settings (API key masked)."""
    s = load_settings()
    return LLMSettingsResponse(
        provider=s.provider,
        api_key_set=bool(s.api_key),
        model=s.model,
        base_url=s.base_url,
        temperature=s.temperature,
        source_directory=s.source_directory,
        work_directory=s.work_directory,
        review_directory=s.review_directory,
        output_directory=s.output_directory,
    )


@router.put("/settings/llm", response_model=LLMSettingsResponse)
async def update_llm_settings(body: LLMSettings) -> LLMSettingsResponse:
    """Update LLM settings. Persisted to settings.json, overrides env defaults."""
    save_settings(body)
    clear_cache()
    s = load_settings()
    return LLMSettingsResponse(
        provider=s.provider,
        api_key_set=bool(s.api_key),
        model=s.model,
        base_url=s.base_url,
        temperature=s.temperature,
        source_directory=s.source_directory,
        work_directory=s.work_directory,
        review_directory=s.review_directory,
        output_directory=s.output_directory,
    )


# ── Spreadsheet Review ───────────────────────────────────────────────────


def _spreadsheet_dir() -> Path | None:
    """Return the directory where spreadsheets live, preferring review_directory,
    falling back to work_directory, then the process cwd."""
    s = load_settings()
    for candidate in (s.review_directory, s.work_directory):
        if candidate:
            p = Path(candidate)
            if p.is_dir():
                return p
    # Fallback: current working directory (where the container runs)
    cwd = Path(".")
    if any(cwd.glob("*.xlsx")):
        return cwd
    return None


@router.get("/spreadsheet/list")
async def list_spreadsheets() -> list[dict[str, str]]:
    """List available spreadsheets in the review/work directory."""
    review_dir = _spreadsheet_dir()
    if not review_dir:
        return []
    files = sorted(review_dir.glob("*.xlsx"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [{"filename": f.name} for f in files]


@router.get("/spreadsheet/download/{filename}")
async def download_spreadsheet(filename: str) -> FileResponse:
    """Download a spreadsheet from the review/work directory."""
    review_dir = _spreadsheet_dir()
    if not review_dir:
        raise HTTPException(status_code=404, detail="No spreadsheet directory available.")

    # Prevent path traversal — only allow plain filenames
    safe_name = Path(filename).name
    file_path = review_dir / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Spreadsheet not found.")

    return FileResponse(
        path=str(file_path.resolve()),
        filename=safe_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/spreadsheet/upload")
async def upload_spreadsheet(file: UploadFile) -> dict[str, str]:
    """Upload a corrected spreadsheet to the review/work directory."""
    s = load_settings()
    # Prefer review_directory, fall back to work_directory, then cwd
    dest_dir_str = s.review_directory or s.work_directory or "."
    dest_dir = Path(dest_dir_str)

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    safe_name = Path(file.filename).name
    if not safe_name.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are accepted.")

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_name

    content = await file.read()
    dest.write_bytes(content)

    return {"path": str(dest), "filename": safe_name}


# ── Document Processing Runs ──────────────────────────────────────────────


@router.post("/runs", response_model=RunStartedResponse, status_code=202)
async def start_run() -> RunStartedResponse:
    """Trigger a new document processing batch run.

    - 400 if SOURCE_DIRECTORY or WORK_DIRECTORY is not configured.
    - 400 if source directory does not exist or contains no valid files.
    - 409 if a run with status='In Progress' already exists.
    """
    settings = load_settings()

    if not settings.source_directory or not settings.work_directory:
        raise HTTPException(
            status_code=400,
            detail=(
                "SOURCE_DIRECTORY and WORK_DIRECTORY must be configured "
                "before triggering a run."
            ),
        )

    # 409 if a batch is already In Progress
    with SessionLocal() as session:
        in_progress = (
            session.query(BatchRunModel)
            .filter(BatchRunModel.status == "In Progress")
            .first()
        )
    if in_progress:
        raise HTTPException(
            status_code=409,
            detail=f"A run is already In Progress (batch_id={in_progress.batch_id}). "
                   "Wait for it to complete before starting a new run.",
        )

    try:
        metadata = run_service.create_batch_run(
            source_dir=settings.source_directory,
            work_dir=settings.work_directory,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    batch_id = metadata["batch_id"]

    # Fire-and-forget: process_batch runs async without blocking the response
    asyncio.create_task(
        run_service.process_batch(
            batch_id=batch_id,
            source_dir=settings.source_directory,
            work_dir=settings.work_directory,
        )
    )

    return RunStartedResponse(
        batch_id=batch_id,
        total_files=metadata["total_files"],
        status=metadata["status"],
    )


@router.get("/runs", response_model=list[BatchRunSummary])
async def list_runs() -> list[BatchRunSummary]:
    """List all batch runs, newest first."""
    with SessionLocal() as session:
        runs = (
            session.query(BatchRunModel)
            .order_by(BatchRunModel.triggered_at.desc())
            .all()
        )
    return [BatchRunSummary.model_validate(r) for r in runs]


@router.get("/runs/{batch_id}", response_model=BatchRunDetail)
async def get_run(batch_id: str) -> BatchRunDetail:
    """Return a single BatchRun with all its RunRecords."""
    with SessionLocal() as session:
        batch_run = session.get(BatchRunModel, batch_id)
        if batch_run is None:
            raise HTTPException(status_code=404, detail=f"Batch run '{batch_id}' not found.")
        run_records = (
            session.query(RunRecordModel)
            .filter(RunRecordModel.batch_id == batch_id)
            .order_by(RunRecordModel.started_at.asc())
            .all()
        )
        detail = BatchRunDetail(
            batch_id=batch_run.batch_id,
            triggered_at=batch_run.triggered_at,
            completed_at=batch_run.completed_at,
            total_files=batch_run.total_files,
            total_records=batch_run.total_records,
            status=batch_run.status,
            run_records=[RunRecordSummary.model_validate(r) for r in run_records],
        )
    return detail


@router.get("/results", response_model=list[PaymentRecordResponse])
async def list_results(
    batch_id: Optional[str] = Query(default=None),
    doc_type: Optional[str] = Query(default=None),
    validation_status: Optional[str] = Query(default=None),
    confidence_min: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    confidence_max: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[PaymentRecordResponse]:
    """List PaymentRecords with optional filters.

    Filters:
    - batch_id: exact match
    - doc_type: exact match (email | remittance | receipt | unknown)
    - validation_status: exact match (Valid | Review Required | Extraction Failed)
    - confidence_min / confidence_max: filter on the overall_confidence column
    - skip / limit: pagination
    """
    with SessionLocal() as session:
        query = session.query(PaymentRecordModel)

        if batch_id:
            query = query.filter(PaymentRecordModel.batch_id == batch_id)
        if doc_type:
            query = query.filter(PaymentRecordModel.doc_type == doc_type)
        if validation_status:
            query = query.filter(PaymentRecordModel.validation_status == validation_status)
        if confidence_min is not None:
            query = query.filter(PaymentRecordModel.overall_confidence >= confidence_min)
        if confidence_max is not None:
            query = query.filter(PaymentRecordModel.overall_confidence <= confidence_max)

        records = (
            query.order_by(PaymentRecordModel.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    return [PaymentRecordResponse.model_validate(r) for r in records]


@router.get("/runs/{batch_id}/stream")
async def stream_run_events(batch_id: str) -> StreamingResponse:
    """SSE endpoint: drain the asyncio.Queue for a batch and stream events.

    Streams AG-UI events as `text/event-stream` frames.
    Closes the stream automatically when a BATCH_COMPLETED event is received.
    """
    # Verify batch exists
    with SessionLocal() as session:
        batch_run = session.get(BatchRunModel, batch_id)
    if batch_run is None:
        raise HTTPException(status_code=404, detail=f"Batch run '{batch_id}' not found.")

    async def _event_generator() -> AsyncGenerator[str, None]:
        queue = run_service._get_queue(batch_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send a keepalive comment to prevent client disconnect
                    yield ": keepalive\n\n"
                    continue

                yield f"data: {json.dumps(event)}\n\n"

                if event.get("event") == "BATCH_COMPLETED":
                    run_service.remove_queue(batch_id)
                    break
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

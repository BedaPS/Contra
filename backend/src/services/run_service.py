"""RunService — orchestrates multi-file document processing pipeline runs.

Responsibilities:
- create_batch_run():  discover source files, create DB records, return batch_id
- process_batch():     sequential per-file graph invocation with AG-UI event emission
- Queue registry:     per-batch asyncio.Queue keyed by batch_id (Decision 5)
- Deduplication:      skips files already Completed in the same batch (Decision 8)

All LLM work is delegated to the DocPipeline graph. RunService is responsible
for orchestration, event emission, and DB state management only.
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.db.engine import SessionLocal
from src.db.models import BatchRunModel, RunRecordModel
from src.graph.doc_pipeline.pipeline import get_doc_pipeline
from src.settings_store import load_settings

# ── Allowed file extensions for source directory scan ──
_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp"}

# ── AG-UI event type names ──
_EVT_BATCH_STARTED = "BATCH_STARTED"
_EVT_FILE_STARTED = "FILE_STARTED"
_EVT_FILE_COMPLETED = "FILE_COMPLETED"
_EVT_FILE_FAILED = "FILE_FAILED"
_EVT_BATCH_COMPLETED = "BATCH_COMPLETED"

# ── Per-batch asyncio.Queue registry ──
# Keyed by batch_id. Consumers (SSE endpoint) drain events from the queue.
_run_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}


def _get_queue(batch_id: str) -> asyncio.Queue[dict[str, Any]]:
    """Return the queue for a batch_id, creating it if needed."""
    if batch_id not in _run_queues:
        _run_queues[batch_id] = asyncio.Queue()
    return _run_queues[batch_id]


def remove_queue(batch_id: str) -> None:
    """Remove the queue for a completed/abandoned batch (called after SSE drains)."""
    _run_queues.pop(batch_id, None)


def _emit(batch_id: str, event: dict[str, Any]) -> None:
    """Put an event into the batch queue (non-blocking, best-effort)."""
    queue = _get_queue(batch_id)
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        pass  # SSE consumer fell behind — events are advisory, not transactional


def _scan_source_files(source_dir: str) -> list[Path]:
    """Return sorted list of allowed file paths in source_dir."""
    src_root = Path(source_dir)
    if not src_root.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source_dir}")
    return sorted(
        f for f in src_root.iterdir()
        if f.is_file() and f.suffix.lower() in _ALLOWED_EXTENSIONS
    )


def _already_completed(batch_id: str, source_filename: str) -> bool:
    """Return True if a RunRecord for this file in this batch is already Completed.

    This implements the deduplication check from Decision 8: if a source file
    was already successfully processed in this batch, skip it.
    """
    with SessionLocal() as session:
        existing = (
            session.query(RunRecordModel)
            .filter(
                RunRecordModel.batch_id == batch_id,
                RunRecordModel.source_filename == source_filename,
                RunRecordModel.status == "Completed",
            )
            .first()
        )
    return existing is not None


def create_batch_run(source_dir: str, work_dir: str) -> dict[str, Any]:
    """Create DB records for a new batch run and return metadata.

    Scans the source directory, creates one RunRecord per discovered file,
    and a BatchRun parent record. Returns the batch_id and file count.
    Does NOT start processing — call process_batch() asynchronously.

    Raises FileNotFoundError if source_dir does not exist or has no files.
    """
    files = _scan_source_files(source_dir)
    if not files:
        raise FileNotFoundError(f"No supported files found in source directory: {source_dir}")

    batch_id = str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)

    with SessionLocal() as session:
        batch_run = BatchRunModel(
            batch_id=batch_id,
            triggered_at=now_utc,
            total_files=len(files),
            total_records=0,
            status="In Progress",
        )
        session.add(batch_run)

        for src_file in files:
            guid_prefix = uuid.uuid4().hex
            guid_filename = f"{guid_prefix}_{src_file.name}"
            work_path = str(Path(work_dir) / guid_filename)

            run_record = RunRecordModel(
                record_id=str(uuid.uuid4()),
                batch_id=batch_id,
                source_filename=src_file.name,
                work_path=work_path,
                guid_filename=guid_filename,
                started_at=now_utc,
                record_count=0,
                status="Pending",
            )
            session.add(run_record)

        session.commit()

    # Initialise the event queue for this batch
    _get_queue(batch_id)

    return {
        "batch_id": batch_id,
        "total_files": len(files),
        "status": "In Progress",
    }


async def process_batch(batch_id: str, source_dir: str, work_dir: str) -> None:
    """Sequentially process each file in the batch through the DocPipeline graph.

    For each file:
    1. Dedup check — skip if already Completed in this batch.
    2. Copy source file to work_dir with GUID-prefixed name.
    3. Set RunRecord.status = 'Processing' BEFORE graph.invoke().
    4. Invoke the DocPipeline graph.
    5. Emit FILE_COMPLETED or FILE_FAILED AG-UI event.

    Emits BATCH_STARTED at the start and BATCH_COMPLETED at the end.
    """
    files = _scan_source_files(source_dir)
    work_path_obj = Path(work_dir)
    work_path_obj.mkdir(parents=True, exist_ok=True)

    _emit(batch_id, {
        "event": _EVT_BATCH_STARTED,
        "batch_id": batch_id,
        "total_files": len(files),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    graph = get_doc_pipeline()
    completed = 0
    failed = 0

    # Load run_records for this batch to get record_id and guid_filename per file
    with SessionLocal() as session:
        run_records = (
            session.query(RunRecordModel)
            .filter(RunRecordModel.batch_id == batch_id)
            .all()
        )
        # Build filename → record mapping (source_filename → RunRecordModel)
        record_map: dict[str, RunRecordModel] = {
            r.source_filename: r for r in run_records
        }

    for src_file in files:
        run_rec = record_map.get(src_file.name)
        if run_rec is None:
            failed += 1
            _emit(batch_id, {
                "event": _EVT_FILE_FAILED,
                "batch_id": batch_id,
                "filename": src_file.name,
                "error": "RunRecord not found for file.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            continue

        run_record_id = run_rec.record_id

        # Deduplication check (Decision 8)
        if _already_completed(batch_id, src_file.name):
            completed += 1
            _emit(batch_id, {
                "event": _EVT_FILE_COMPLETED,
                "batch_id": batch_id,
                "filename": src_file.name,
                "run_record_id": run_record_id,
                "skipped": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            continue

        # Copy source file to work directory with GUID-prefixed name
        work_file_path = str(work_path_obj / run_rec.guid_filename)
        try:
            shutil.copy2(str(src_file), work_file_path)
        except OSError as exc:
            _mark_run_record_failed(run_record_id)
            failed += 1
            _emit(batch_id, {
                "event": _EVT_FILE_FAILED,
                "batch_id": batch_id,
                "filename": src_file.name,
                "run_record_id": run_record_id,
                "error": f"Failed to copy to work directory: {exc}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            continue

        # Set RunRecord.status = 'Processing' BEFORE graph invocation (Decision spec)
        _set_run_record_status(run_record_id, "Processing")

        _emit(batch_id, {
            "event": _EVT_FILE_STARTED,
            "batch_id": batch_id,
            "filename": src_file.name,
            "run_record_id": run_record_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Invoke DocPipeline graph
        initial_state: dict[str, Any] = {
            "batch_id": batch_id,
            "run_record_id": run_record_id,
            "source_file_path": str(src_file),
            "work_file_path": work_file_path,
            "guid_filename": run_rec.guid_filename,
            "extraction_attempts": 0,
            "error": None,
            "error_type": None,
        }

        try:
            # graph.invoke() is synchronous; run in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            final_state = await loop.run_in_executor(None, graph.invoke, initial_state)

            if final_state.get("error"):
                failed += 1
                _emit(batch_id, {
                    "event": _EVT_FILE_FAILED,
                    "batch_id": batch_id,
                    "filename": src_file.name,
                    "run_record_id": run_record_id,
                    "error": str(final_state.get("error", ""))[:500],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            else:
                completed += 1
                _emit(batch_id, {
                    "event": _EVT_FILE_COMPLETED,
                    "batch_id": batch_id,
                    "filename": src_file.name,
                    "run_record_id": run_record_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        except Exception as exc:
            _mark_run_record_failed(run_record_id)
            failed += 1
            _emit(batch_id, {
                "event": _EVT_FILE_FAILED,
                "batch_id": batch_id,
                "filename": src_file.name,
                "run_record_id": run_record_id,
                "error": f"{type(exc).__name__}: {str(exc)[:400]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    # Update BatchRun final status
    batch_status = "Completed" if failed == 0 else ("Failed" if completed == 0 else "Completed")
    _finalise_batch(batch_id, batch_status)

    _emit(batch_id, {
        "event": _EVT_BATCH_COMPLETED,
        "batch_id": batch_id,
        "completed": completed,
        "failed": failed,
        "status": batch_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def _set_run_record_status(run_record_id: str, status: str) -> None:
    with SessionLocal() as session:
        rec = session.get(RunRecordModel, run_record_id)
        if rec:
            rec.status = status
            session.commit()


def _mark_run_record_failed(run_record_id: str) -> None:
    with SessionLocal() as session:
        rec = session.get(RunRecordModel, run_record_id)
        if rec:
            rec.status = "Failed"
            rec.completed_at = datetime.now(timezone.utc)
            session.commit()


def _finalise_batch(batch_id: str, status: str) -> None:
    with SessionLocal() as session:
        batch_run = session.get(BatchRunModel, batch_id)
        if batch_run:
            batch_run.status = status
            batch_run.completed_at = datetime.now(timezone.utc)
            session.commit()

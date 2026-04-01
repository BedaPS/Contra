"""SSE endpoint streaming AG-UI protocol events from the LangGraph pipeline.

Runs the LangGraph reconciliation graph and translates state updates into
AG-UI events: RUN_STARTED, STEP_STARTED, TEXT_MESSAGE_*, STATE_SNAPSHOT,
STEP_FINISHED, RUN_FINISHED.

Also provides a /agents/resume endpoint for HITL interrupt resolution.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.audit import logger as audit_log
from src.graph.pipeline import get_pipeline
from src.graph.state import ContraState

router = APIRouter(prefix="/api/v1")

# ---------------------------------------------------------------------------
# Default input for demo runs
# ---------------------------------------------------------------------------

DEFAULT_INPUT: ContraState = {
    "document_id": "DOC-2026-00142",
    "source_email": "payments@acmecorp.co.za",
    "attachment_mime_type": "application/pdf",
    "raw_text": "Invoice from ACME Corporation for ZAR 15,750.00",
    "ocr_fields": {
        "account_name": {"value": "ACME Corporation (Pty) Ltd", "confidence_score": 0.97},
        "amount": {"value": "15750.00", "confidence_score": 0.99},
        "currency": {"value": "ZAR", "confidence_score": 1.0},
        "bank_reference_id": {"value": "FNB-REF-8843921", "confidence_score": 0.94},
        "payment_date": {"value": "2026-03-20", "confidence_score": 0.96},
    },
    "document_state": "NEW",
    "bank_candidates": [
        {
            "transaction_id": "BNK-TXN-991204",
            "account_name": "ACME Corp Pty Ltd",
            "amount": 15750.00,
            "date": "2026-03-20",
            "reference_id": "FNB-REF-8843921",
        },
        {
            "transaction_id": "BNK-TXN-991207",
            "account_name": "Globex International",
            "amount": 22300.00,
            "date": "2026-03-19",
            "reference_id": "STD-REF-7712003",
        },
    ],
    "match_result": None,
    "error": None,
    "messages": [],
}

# Node → step name mapping for AG-UI events
_NODE_LABELS = {
    "ingest": "ingestion_agent",
    "ocr_extract": "ocr_agent",
    "enrich": "enrichment_agent",
    "build_spreadsheet": "spreadsheet_builder",
    "spreadsheet_review": "spreadsheet_review",
    "match": "auditor_agent",
    "finalize": "finalization",
    "human_review": "human_review",
    "error_handler": "error_handler",
}


# Module-level cache of the last pipeline run's documents
_last_run_documents: list[dict] = []


def _safe_float(value: Any) -> float:
    """Safely convert a value to float."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _field_value(field: Any, default: str = "") -> str:
    """Extract 'value' from an OCR field that may be a dict, tuple, or primitive."""
    if field is None:
        return default
    if isinstance(field, dict):
        return str(field.get("value", default))
    if isinstance(field, (tuple, list)) and len(field) > 0:
        return str(field[0])
    return str(field)


def _field_confidence(field: Any) -> float:
    """Extract confidence_score from an OCR field (dict, tuple, or primitive)."""
    if isinstance(field, dict):
        return float(field.get("confidence_score", 0))
    if isinstance(field, (tuple, list)) and len(field) > 1:
        try:
            return float(field[1])
        except (ValueError, TypeError):
            return 0.0
    return 0.0


def _event(event_type: str, data: dict) -> str:
    """Format a single SSE event line."""
    payload = {"type": event_type, "timestamp": time.time(), **data}
    return f"data: {json.dumps(payload)}\n\n"


def _state_snapshot(state: dict[str, Any], node_name: str) -> dict:
    """Build a STATE_SNAPSHOT payload from the current graph state."""
    from src.graph.pipeline import HAPPY_PATH_NODES
    pipeline = [n["label"] for n in HAPPY_PATH_NODES]
    node_ids = [n["id"] for n in HAPPY_PATH_NODES]
    doc_state = state.get("document_state", "")

    # Map document states to node ids for completion tracking
    _state_to_node = {
        "Ingested": "ingest",
        "Parsed": "ocr_extract",
        "Enriched": "enrich",
        "Spreadsheet_Built": "build_spreadsheet",
        "Spreadsheet_Approved": "spreadsheet_review",
        "Matched": "match",
        "Finalized": "finalize",
    }

    current_node = _state_to_node.get(doc_state, "")
    completed: list[str] = []
    for nid, label in zip(node_ids, pipeline):
        completed.append(label)
        if nid == current_node:
            break

    # Build document list with flat fields extracted from ocr_fields
    ocr_fields = state.get("ocr_fields", {})
    file_records = state.get("file_records") or []
    documents: list[dict[str, Any]] = []

    if file_records:
        for rec in file_records:
            rf = rec.get("ocr_fields") or {} if isinstance(rec, dict) else {}
            documents.append({
                "document_id": rec.get("file_id", "") if isinstance(rec, dict) else "",
                "state": rec.get("status", doc_state) if isinstance(rec, dict) else doc_state,
                "source_email": state.get("source_email", ""),
                "account_name": _field_value(rf.get("account_name")),
                "amount": _safe_float(_field_value(rf.get("amount"), "0")),
                "currency": _field_value(rf.get("currency"), "ZAR"),
                "payment_date": _field_value(rf.get("payment_date")),
                "bank_reference_id": _field_value(rf.get("bank_reference_id")) or None,
                "attachment_mime_type": rec.get("mime_type", "") if isinstance(rec, dict) else "",
                "ocr_confidence": {k: _field_confidence(v) for k, v in rf.items()},
            })
    else:
        # Single-file / demo mode
        documents.append({
            "document_id": state.get("document_id", ""),
            "state": doc_state,
            "source_email": state.get("source_email", ""),
            "account_name": _field_value(ocr_fields.get("account_name")),
            "amount": _safe_float(_field_value(ocr_fields.get("amount"), "0")),
            "currency": _field_value(ocr_fields.get("currency"), "ZAR"),
            "payment_date": _field_value(ocr_fields.get("payment_date")),
            "bank_reference_id": _field_value(ocr_fields.get("bank_reference_id")) or None,
            "attachment_mime_type": state.get("attachment_mime_type", ""),
            "ocr_confidence": {k: _field_confidence(v) for k, v in ocr_fields.items()},
        })

    return {
        "documents": documents,
        "currentStep": _NODE_LABELS.get(node_name, node_name),
        "pipeline": pipeline,
        "completedSteps": completed,
        "matchResult": state.get("match_result"),
        "error": state.get("error"),
        "spreadsheetPath": state.get("review_spreadsheet_path") or state.get("spreadsheet_path"),
    }


async def _stream_graph_events(
    input_state: ContraState | None = None,
    thread_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Run the LangGraph pipeline and yield AG-UI SSE events."""
    global _last_run_documents
    pipeline = get_pipeline()
    run_id = str(uuid.uuid4())
    thread_id = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    yield _event("RUN_STARTED", {"runId": run_id, "threadId": thread_id})

    state_input = input_state or DEFAULT_INPUT

    try:
        for event in pipeline.stream(state_input, config=config, stream_mode="updates"):
            for node_name, node_output in event.items():
                # Skip non-dict outputs (e.g. interrupt markers)
                if not isinstance(node_output, dict):
                    continue

                step_id = str(uuid.uuid4())
                step_label = _NODE_LABELS.get(node_name, node_name)

                yield _event("STEP_STARTED", {
                    "stepName": step_label,
                    "stepId": step_id,
                    "runId": run_id,
                })

                # Extract messages from node output for text streaming
                messages = node_output.get("messages", [])
                for msg in messages:
                    msg_id = str(uuid.uuid4())
                    content = msg.content if hasattr(msg, "content") else str(msg)
                    yield _event("TEXT_MESSAGE_START", {"messageId": msg_id, "role": "assistant"})
                    yield _event("TEXT_MESSAGE_CONTENT", {"messageId": msg_id, "content": content})
                    yield _event("TEXT_MESSAGE_END", {"messageId": msg_id})

                # Get the latest state snapshot from the graph
                current_state = pipeline.get_state(config)
                snapshot_values = current_state.values if current_state else node_output
                snapshot = _state_snapshot(snapshot_values, node_name)
                _last_run_documents = snapshot["documents"]
                yield _event("STATE_SNAPSHOT", {"snapshot": snapshot})

                yield _event("STEP_FINISHED", {
                    "stepName": step_label,
                    "stepId": step_id,
                    "runId": run_id,
                })

                await asyncio.sleep(0.05)

    except Exception as exc:
        yield _event("RUN_ERROR", {"runId": run_id, "error": str(exc)})

    # Check if the graph is suspended at an interrupt (HITL)
    try:
        graph_state = pipeline.get_state(config)
        if graph_state and graph_state.next:
            # Graph is paused — emit interrupt event with context
            interrupt_data: dict[str, Any] = {
                "runId": run_id,
                "threadId": thread_id,
                "pausedBefore": list(graph_state.next),
            }
            # Extract interrupt context from tasks if available
            if hasattr(graph_state, "tasks") and graph_state.tasks:
                for task in graph_state.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        interrupt_data["context"] = task.interrupts[0].value
                        break
            yield _event("HITL_INTERRUPT", interrupt_data)
    except Exception:
        pass  # Non-critical — proceed to RUN_FINISHED

    yield _event("RUN_FINISHED", {"runId": run_id, "threadId": thread_id})


@router.get("/agents/stream")
async def stream_pipeline():
    """SSE endpoint — streams AG-UI protocol events from the LangGraph pipeline."""
    return StreamingResponse(
        _stream_graph_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agents/resume")
async def resume_pipeline(thread_id: str, review: dict[str, Any]):
    """Resume a paused pipeline after HITL review.

    Body: {"reviewer_id": str, "action": "approve"|"reject"|"correct",
           "rationale": str, "corrected_data": {...} | null}
    """
    from langgraph.types import Command

    pipeline = get_pipeline()
    config = {"configurable": {"thread_id": thread_id}}

    async def _stream_resume() -> AsyncGenerator[str, None]:
        global _last_run_documents
        run_id = str(uuid.uuid4())
        yield _event("RUN_STARTED", {"runId": run_id, "threadId": thread_id})

        try:
            for event in pipeline.stream(Command(resume=review), config=config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    # Skip non-dict outputs (e.g. interrupt markers)
                    if not isinstance(node_output, dict):
                        continue

                    step_id = str(uuid.uuid4())
                    step_label = _NODE_LABELS.get(node_name, node_name)

                    yield _event("STEP_STARTED", {
                        "stepName": step_label,
                        "stepId": step_id,
                        "runId": run_id,
                    })

                    messages = node_output.get("messages", [])
                    for msg in messages:
                        msg_id = str(uuid.uuid4())
                        content = msg.content if hasattr(msg, "content") else str(msg)
                        yield _event("TEXT_MESSAGE_START", {"messageId": msg_id, "role": "assistant"})
                        yield _event("TEXT_MESSAGE_CONTENT", {"messageId": msg_id, "content": content})
                        yield _event("TEXT_MESSAGE_END", {"messageId": msg_id})

                    current_state = pipeline.get_state(config)
                    snapshot_values = current_state.values if current_state else node_output
                    snapshot = _state_snapshot(snapshot_values, node_name)
                    _last_run_documents = snapshot["documents"]
                    yield _event("STATE_SNAPSHOT", {"snapshot": snapshot})

                    yield _event("STEP_FINISHED", {
                        "stepName": step_label,
                        "stepId": step_id,
                        "runId": run_id,
                    })

                    await asyncio.sleep(0.05)

        except Exception as exc:
            yield _event("RUN_ERROR", {"runId": run_id, "error": str(exc)})

        # Check for another interrupt after resume
        try:
            graph_state = pipeline.get_state(config)
            if graph_state and graph_state.next:
                interrupt_data: dict[str, Any] = {
                    "runId": run_id,
                    "threadId": thread_id,
                    "pausedBefore": list(graph_state.next),
                }
                if hasattr(graph_state, "tasks") and graph_state.tasks:
                    for task in graph_state.tasks:
                        if hasattr(task, "interrupts") and task.interrupts:
                            interrupt_data["context"] = task.interrupts[0].value
                            break
                yield _event("HITL_INTERRUPT", interrupt_data)
        except Exception:
            pass

        yield _event("RUN_FINISHED", {"runId": run_id, "threadId": thread_id})

    return StreamingResponse(
        _stream_resume(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Data endpoints — return real data from pipeline runs
# ---------------------------------------------------------------------------

@router.get("/documents")
async def list_documents():
    """Return documents from the last pipeline run."""
    return _last_run_documents


@router.get("/audit/entries")
async def list_audit_entries():
    """Return real audit trail entries from the pipeline."""
    return [e.model_dump() for e in audit_log.entries()]

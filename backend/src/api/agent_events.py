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
    "pii_redact": "pii_redaction",
    "match": "auditor_agent",
    "finalize": "finalization",
    "human_review": "human_review",
    "error_handler": "error_handler",
}


def _event(event_type: str, data: dict) -> str:
    """Format a single SSE event line."""
    payload = {"type": event_type, "timestamp": time.time(), **data}
    return f"data: {json.dumps(payload)}\n\n"


def _state_snapshot(state: dict[str, Any], node_name: str) -> dict:
    """Build a STATE_SNAPSHOT payload from the current graph state."""
    pipeline = ["Ingested", "Parsed", "PII_Redacted", "Matched", "Finalized"]
    doc_state = state.get("document_state", "")

    completed = []
    for s in pipeline:
        completed.append(s)
        if s == doc_state:
            break

    return {
        "documents": [{
            "document_id": state.get("document_id", ""),
            "state": doc_state,
            "source_email": state.get("source_email", ""),
            "ocr_fields": state.get("ocr_fields", {}),
        }],
        "currentStep": _NODE_LABELS.get(node_name, node_name),
        "pipeline": pipeline,
        "completedSteps": completed,
        "matchResult": state.get("match_result"),
        "error": state.get("error"),
    }


async def _stream_graph_events(
    input_state: ContraState | None = None,
    thread_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Run the LangGraph pipeline and yield AG-UI SSE events."""
    pipeline = get_pipeline()
    run_id = str(uuid.uuid4())
    thread_id = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    yield _event("RUN_STARTED", {"runId": run_id, "threadId": thread_id})

    state_input = input_state or DEFAULT_INPUT

    try:
        for event in pipeline.stream(state_input, config=config, stream_mode="updates"):
            for node_name, node_output in event.items():
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
                yield _event("STATE_SNAPSHOT", {
                    "snapshot": _state_snapshot(snapshot_values, node_name),
                })

                yield _event("STEP_FINISHED", {
                    "stepName": step_label,
                    "stepId": step_id,
                    "runId": run_id,
                })

                await asyncio.sleep(0.05)

    except Exception as exc:
        yield _event("RUN_ERROR", {"runId": run_id, "error": str(exc)})

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
        run_id = str(uuid.uuid4())
        yield _event("RUN_STARTED", {"runId": run_id, "threadId": thread_id})

        try:
            for event in pipeline.stream(Command(resume=review), config=config, stream_mode="updates"):
                for node_name, node_output in event.items():
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
                    yield _event("STATE_SNAPSHOT", {
                        "snapshot": _state_snapshot(snapshot_values, node_name),
                    })

                    yield _event("STEP_FINISHED", {
                        "stepName": step_label,
                        "stepId": step_id,
                        "runId": run_id,
                    })

                    await asyncio.sleep(0.05)

        except Exception as exc:
            yield _event("RUN_ERROR", {"runId": run_id, "error": str(exc)})

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
# Static mock data endpoints for the dashboard screens
# ---------------------------------------------------------------------------

@router.get("/documents")
async def list_documents():
    """Return mock documents at various pipeline stages."""
    return [
        {
            "document_id": "DOC-2026-00142",
            "source_email": "[REDACTED]",
            "account_name": "ACME Corporation (Pty) Ltd",
            "amount": 15750.00,
            "currency": "ZAR",
            "state": "Finalized",
            "payment_date": "2026-03-20",
            "created_at": "2026-03-20T08:14:22Z",
        },
        {
            "document_id": "DOC-2026-00143",
            "source_email": "[REDACTED]",
            "account_name": "Globex International",
            "amount": 22300.00,
            "currency": "ZAR",
            "state": "Needs_Review",
            "payment_date": "2026-03-19",
            "created_at": "2026-03-20T09:02:11Z",
            "review_reason": "OCR confidence for amount field (0.72) below 0.85 threshold.",
        },
        {
            "document_id": "DOC-2026-00144",
            "source_email": "[REDACTED]",
            "account_name": "Initech Systems",
            "amount": 8400.00,
            "currency": "ZAR",
            "state": "Human_Review",
            "payment_date": "2026-03-18",
            "created_at": "2026-03-20T10:30:45Z",
            "review_reason": "Duplicate bank transactions detected — both LOCKED pending human decision.",
        },
        {
            "document_id": "DOC-2026-00145",
            "source_email": "[REDACTED]",
            "account_name": "Umbrella Corp",
            "amount": 5200.00,
            "currency": "ZAR",
            "state": "PII_Redacted",
            "payment_date": "2026-03-21",
            "created_at": "2026-03-21T07:45:00Z",
        },
        {
            "document_id": "DOC-2026-00146",
            "source_email": "[REDACTED]",
            "account_name": "Stark Industries",
            "amount": 42000.00,
            "currency": "ZAR",
            "state": "Matched",
            "payment_date": "2026-03-21",
            "created_at": "2026-03-21T11:20:33Z",
        },
    ]


@router.get("/audit/entries")
async def list_audit_entries():
    """Return mock audit trail entries."""
    return [
        {
            "agent": "ingestion_agent",
            "timestamp": "2026-03-20T08:14:22Z",
            "input_hash": "a3f1c2...d4e5",
            "output_hash": "b7c8d9...e0f1",
            "state_from": "Ingested",
            "state_to": "Parsed",
            "decision": "ADVANCE",
            "rationale": "MIME type application/pdf valid. All required fields present.",
            "confidence_scores": {"account_name": 0.97, "amount": 0.99, "payment_date": 0.96},
        },
        {
            "agent": "ingestion_agent",
            "timestamp": "2026-03-20T08:14:23Z",
            "input_hash": "b7c8d9...e0f1",
            "output_hash": "c1d2e3...f4g5",
            "state_from": "Parsed",
            "state_to": "PII_Redacted",
            "decision": "ADVANCE",
            "rationale": "Email masked to [REDACTED]. Raw text cleared.",
            "confidence_scores": {},
        },
        {
            "agent": "auditor_agent",
            "timestamp": "2026-03-20T08:14:25Z",
            "input_hash": "c1d2e3...f4g5",
            "output_hash": "d5e6f7...g8h9",
            "state_from": "PII_Redacted",
            "state_to": "Matched",
            "decision": "MATCHED",
            "rationale": "Bank Ref ID FNB-REF-8843921 exact match with BNK-TXN-991204. Delta $0.00.",
            "confidence_scores": {"bank_ref_match": 1.0, "amount_match": 1.0},
        },
        {
            "agent": "ocr_agent",
            "timestamp": "2026-03-20T09:02:15Z",
            "input_hash": "e3f4g5...h6i7",
            "output_hash": "f7g8h9...i0j1",
            "state_from": "Ingested",
            "state_to": "Needs_Review",
            "decision": "BLOCKED",
            "rationale": "Field 'amount' confidence 0.72 below 0.85 threshold. Requires manual review.",
            "confidence_scores": {"account_name": 0.91, "amount": 0.72, "payment_date": 0.88},
        },
        {
            "agent": "auditor_agent",
            "timestamp": "2026-03-20T10:30:50Z",
            "input_hash": "g5h6i7...j8k9",
            "output_hash": "h9i0j1...k2l3",
            "state_from": "PII_Redacted",
            "state_to": "Human_Review",
            "decision": "LOCKED",
            "rationale": "Duplicate candidates: BNK-TXN-993401 and BNK-TXN-993402 identical. Both LOCKED.",
            "confidence_scores": {"name_sim_1": 0.95, "name_sim_2": 0.95},
        },
    ]

"""LangGraph node functions for the reconciliation pipeline.

Each function receives the full ContraState and returns a partial update dict.
Gate checks are performed before state transitions. Failures return error state.

Batch processing: ingest scans the source directory for all matching files,
ocr_extract processes each file and writes structured JSON, enrich processes
files in parallel, and build_spreadsheet aggregates all records into Excel.
"""

from __future__ import annotations

import json
import mimetypes
import re
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.types import interrupt
from Levenshtein import ratio as levenshtein_ratio

from src.audit import logger as audit_log
from src.audit.logger import AuditEntry, compute_hash
from src.graph.state import ContraState, FileRecord
from src.settings_store import load_settings

# ── Constitution thresholds ──
_ALLOWED_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff", "image/webp"}
_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp"}
CONFIDENCE_THRESHOLD = 0.85
NAME_SIMILARITY_THRESHOLD = 0.90
TEMPORAL_WINDOW_DAYS = 7
MAX_CYCLE_ITERATIONS = 3


def _mime_for_file(path: Path) -> str:
    """Derive MIME type from file extension."""
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


# ---------------------------------------------------------------------------
# Node: ingest (batch)
# ---------------------------------------------------------------------------

def ingest_node(state: ContraState) -> dict[str, Any]:
    """Scan source directory for all matching files, copy each to work dir.

    Populates file_records with one entry per discovered file.
    Requires SOURCE_DIRECTORY to be configured — fails with Error_Queue
    if the setting is missing or the directory does not exist.
    """
    settings = load_settings()
    source_dir = settings.source_directory
    work_dir_str = settings.work_directory
    batch_id = state.get("batch_id") or f"BATCH-{uuid.uuid4().hex[:8].upper()}"

    # SOURCE_DIRECTORY is required — no silent demo fallback.
    if not source_dir:
        _log_transition("ingestion_agent", state, "NEW", "Error_Queue",
                        "ERROR", "SOURCE_DIRECTORY is not configured.")
        return {
            "batch_id": batch_id,
            "document_state": "Error_Queue",
            "error": "SOURCE_DIRECTORY is not configured. Set it in Settings before running the pipeline.",
            "messages": [AIMessage(content="[ingestion_agent] ERROR — SOURCE_DIRECTORY is not configured.")],
        }

    src_root = Path(source_dir)
    if not src_root.is_dir():
        _log_transition("ingestion_agent", state, "NEW", "Error_Queue",
                        "ERROR", f"Source directory not found: {source_dir}")
        return {
            "document_state": "Error_Queue",
            "error": f"Source directory not found: {source_dir}",
            "messages": [AIMessage(content=f"[ingestion_agent] ERROR — source dir not found: {source_dir}")],
        }

    # Discover matching files
    discovered: list[Path] = sorted(
        f for f in src_root.iterdir()
        if f.is_file() and f.suffix.lower() in _ALLOWED_EXTENSIONS
    )

    if not discovered:
        _log_transition("ingestion_agent", state, "NEW", "Error_Queue",
                        "ERROR", "No matching files in source directory.")
        return {
            "batch_id": batch_id,
            "document_state": "Error_Queue",
            "error": "No matching files found in source directory.",
            "messages": [AIMessage(content="[ingestion_agent] No matching files found.")],
        }

    # Set up work directory
    work_root = Path(work_dir_str) if work_dir_str else src_root / "_work"
    work_root.mkdir(parents=True, exist_ok=True)

    file_records: list[FileRecord] = []
    for src_file in discovered:
        file_id = f"FILE-{uuid.uuid4().hex[:8].upper()}"
        dest = work_root / f"{file_id}_{src_file.name}"
        shutil.copy2(str(src_file), str(dest))
        file_records.append(FileRecord(
            file_id=file_id,
            source_path=str(src_file),
            work_path=str(dest),
            mime_type=_mime_for_file(src_file),
            status="pending",
            ocr_fields={},
            ocr_json_path=None,
            error=None,
        ))

    count = len(file_records)
    _log_transition("ingestion_agent", state, "NEW", "Ingested",
                    "OK", f"Batch {batch_id}: {count} file(s) ingested from {source_dir}.")

    return {
        "batch_id": batch_id,
        "document_id": batch_id,
        "document_state": "Ingested",
        "file_records": file_records,
        "error": None,
        "messages": [AIMessage(
            content=f"[ingestion_agent] Batch {batch_id}: {count} file(s) copied to work directory."
        )],
    }


# ---------------------------------------------------------------------------
# Node: ocr_extract (batch — iterates file_records, writes JSON per file)
# ---------------------------------------------------------------------------

def ocr_extract_node(state: ContraState) -> dict[str, Any]:
    """Extract/validate OCR fields for every file in the batch.

    For each file_record, runs OCR (stub — uses state ocr_fields for demo)
    and writes a structured JSON output file alongside the work copy.

    In production, this node would call the LLM adapter per file.
    """
    file_records: list[FileRecord] = list(state.get("file_records") or [])
    doc_id = state.get("document_id", "")
    batch_ocr_fields = state.get("ocr_fields", {})

    # If no file_records (single-file / demo mode) — use legacy behaviour
    if not file_records:
        return _ocr_extract_single(state, batch_ocr_fields, doc_id)

    all_ok = True
    low_confidence_files: list[str] = []
    messages: list[AIMessage] = []
    updated_records: list[FileRecord] = []

    for rec in file_records:
        # In production, invoke LLM adapter with rec["work_path"].
        # For now, stub: assign the shared ocr_fields to every file.
        fields = dict(batch_ocr_fields) if batch_ocr_fields else {
            "account_name": {"value": f"Account for {rec['file_id']}", "confidence_score": 0.95},
            "amount": {"value": "0.00", "confidence_score": 0.95},
            "currency": {"value": "ZAR", "confidence_score": 1.0},
            "payment_date": {"value": "2026-01-01", "confidence_score": 0.95},
        }

        # Gate: required fields
        amount_field = fields.get("amount", {})
        account_field = fields.get("account_name", {})

        if not amount_field.get("value") or not account_field.get("value"):
            rec_copy = dict(rec)
            rec_copy["status"] = "error"
            rec_copy["error"] = "Required OCR fields missing."
            rec_copy["ocr_fields"] = fields
            updated_records.append(FileRecord(**rec_copy))
            all_ok = False
            continue

        # Check confidence
        low = [n for n, f in fields.items() if f.get("confidence_score", 0.0) < CONFIDENCE_THRESHOLD]
        if low:
            low_confidence_files.append(rec["file_id"])
            all_ok = False

        # Write structured JSON output
        json_path = _write_ocr_json(rec["work_path"], rec["file_id"], fields)

        rec_copy = dict(rec)
        rec_copy["status"] = "ocr_done"
        rec_copy["ocr_fields"] = fields
        rec_copy["ocr_json_path"] = json_path
        updated_records.append(FileRecord(**rec_copy))

        messages.append(AIMessage(
            content=f"[ocr_agent] OCR complete for {rec['file_id']}. JSON written to {json_path}."
        ))

    # Determine overall state
    if low_confidence_files:
        _log_transition("ocr_agent", state, "Ingested", "Needs_Review",
                        "BLOCKED", f"Low confidence in: {', '.join(low_confidence_files)}")
        return {
            "document_state": "Needs_Review",
            "file_records": updated_records,
            "error": f"Low confidence files: {', '.join(low_confidence_files)}",
            "messages": messages + [AIMessage(
                content=f"[ocr_agent] BLOCKED — low confidence in {len(low_confidence_files)} file(s)."
            )],
        }

    if not all_ok:
        error_ids = [r["file_id"] for r in updated_records if r.get("status") == "error"]
        _log_transition("ocr_agent", state, "Ingested", "Needs_Review",
                        "BLOCKED", f"Errors in files: {', '.join(error_ids)}")
        return {
            "document_state": "Needs_Review",
            "file_records": updated_records,
            "error": f"OCR errors in: {', '.join(error_ids)}",
            "messages": messages,
        }

    _log_transition("ocr_agent", state, "Ingested", "Parsed",
                    "OK", f"All {len(updated_records)} files passed OCR.")

    return {
        "document_state": "Parsed",
        "file_records": updated_records,
        "error": None,
        "messages": messages + [AIMessage(
            content=f"[ocr_agent] Batch OCR complete: {len(updated_records)} file(s) parsed."
        )],
    }


def _ocr_extract_single(state: ContraState, ocr_fields: dict, doc_id: str) -> dict[str, Any]:
    """Legacy single-file OCR extraction (demo mode)."""
    amount_field = ocr_fields.get("amount", {})
    account_field = ocr_fields.get("account_name", {})

    if not amount_field.get("value") or not account_field.get("value"):
        _log_transition("ocr_agent", state, "Ingested", "Incomplete_Data",
                        "ERROR", "Required fields (amount or account_name) missing or null.")
        return {
            "document_state": "Incomplete_Data",
            "error": "Required OCR fields missing.",
            "messages": [AIMessage(content="[ocr_agent] BLOCKED — required fields missing.")],
        }

    low_confidence = [
        name for name, field in ocr_fields.items()
        if field.get("confidence_score", 0.0) < CONFIDENCE_THRESHOLD
    ]
    confidence_msg = "; ".join(
        f"{n}: {ocr_fields[n].get('confidence_score', 0):.2f}" for n in ocr_fields
    )

    if low_confidence:
        _log_transition("ocr_agent", state, "Ingested", "Needs_Review",
                        "BLOCKED", f"Low confidence fields: {', '.join(low_confidence)}")
        return {
            "document_state": "Needs_Review",
            "error": f"Low confidence: {', '.join(low_confidence)}",
            "messages": [AIMessage(
                content=f"[ocr_agent] Fields extracted ({confidence_msg}). "
                        f"BLOCKED — low confidence: {', '.join(low_confidence)}"
            )],
        }

    _log_transition("ocr_agent", state, "Ingested", "Parsed",
                    "OK", f"All fields above threshold. {confidence_msg}")
    return {
        "document_state": "Parsed",
        "error": None,
        "messages": [AIMessage(
            content=f"[ocr_agent] OCR complete for {doc_id}. {confidence_msg}. All above 0.85 threshold."
        )],
    }


def _write_ocr_json(work_path: str, file_id: str, fields: dict) -> str:
    """Write structured OCR output as a JSON file alongside the work copy."""
    work = Path(work_path)
    json_path = work.parent / f"{file_id}_ocr.json"
    payload = {
        "file_id": file_id,
        "source_file": work.name,
        "ocr_fields": fields,
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(json_path)


# ---------------------------------------------------------------------------
# Node: enrich (batch — parallel enrichment of all files)
# ---------------------------------------------------------------------------

def _enrich_single_record(rec: FileRecord) -> FileRecord:
    """Enrich a single file record (runs inside thread pool)."""
    fields = dict(rec.get("ocr_fields") or {})

    # --- Normalise amount format ---
    amount_field = fields.get("amount", {})
    if amount_field.get("value"):
        raw_val = str(amount_field["value"]).strip()
        cleaned = re.sub(r"[^\d.\-,]", "", raw_val).replace(",", "")
        if cleaned != raw_val:
            fields["amount"] = {**amount_field, "value": cleaned, "enriched": True}

    # --- Normalise date to YYYY-MM-DD ---
    date_field = fields.get("payment_date", {})
    if date_field.get("value"):
        parsed = _parse_date(date_field["value"])
        if parsed:
            iso_date = parsed.isoformat()
            if iso_date != date_field["value"]:
                fields["payment_date"] = {**date_field, "value": iso_date, "enriched": True}

    # --- Trim whitespace from account name ---
    name_field = fields.get("account_name", {})
    if name_field.get("value"):
        trimmed = str(name_field["value"]).strip()
        if trimmed != name_field["value"]:
            fields["account_name"] = {**name_field, "value": trimmed, "enriched": True}

    # Write enriched JSON back (overwrite OCR json)
    if rec.get("ocr_json_path"):
        json_path = Path(rec["ocr_json_path"])
        payload = {
            "file_id": rec["file_id"],
            "source_file": Path(rec["work_path"]).name,
            "ocr_fields": fields,
            "enriched": True,
        }
        json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    updated = dict(rec)
    updated["ocr_fields"] = fields
    updated["status"] = "enriched"
    return FileRecord(**updated)


def enrich_node(state: ContraState) -> dict[str, Any]:
    """Enrich OCR-extracted fields — processes batch file_records in parallel.

    Falls back to single-file enrichment when file_records is empty (demo mode).
    """
    file_records: list[FileRecord] = list(state.get("file_records") or [])
    doc_id = state.get("document_id", "")

    # --- Single-file / demo fallback ---
    if not file_records:
        return _enrich_single_fields(state, doc_id)

    # --- Parallel enrichment of all file records ---
    enriched_records: list[FileRecord] = []
    with ThreadPoolExecutor(max_workers=min(len(file_records), 8)) as pool:
        futures = {pool.submit(_enrich_single_record, rec): rec for rec in file_records}
        for future in as_completed(futures):
            enriched_records.append(future.result())

    # Sort back into original order
    order = {rec["file_id"]: i for i, rec in enumerate(file_records)}
    enriched_records.sort(key=lambda r: order.get(r["file_id"], 0))

    _log_transition("enrichment_agent", state, "Parsed", "Enriched",
                    "OK", f"Batch enrichment complete: {len(enriched_records)} file(s).")

    return {
        "file_records": enriched_records,
        "document_state": "Enriched",
        "error": None,
        "messages": [AIMessage(
            content=f"[enrichment_agent] Parallel enrichment complete for {len(enriched_records)} file(s)."
        )],
    }


def _enrich_single_fields(state: ContraState, doc_id: str) -> dict[str, Any]:
    """Enrich single-file OCR fields (demo/legacy fallback)."""
    ocr_fields = state.get("ocr_fields", {})
    enriched = dict(ocr_fields)

    amount_field = enriched.get("amount", {})
    if amount_field.get("value"):
        raw_val = str(amount_field["value"]).strip()
        cleaned = re.sub(r"[^\d.\-,]", "", raw_val).replace(",", "")
        if cleaned != raw_val:
            enriched["amount"] = {**amount_field, "value": cleaned, "enriched": True}

    date_field = enriched.get("payment_date", {})
    if date_field.get("value"):
        parsed = _parse_date(date_field["value"])
        if parsed:
            iso_date = parsed.isoformat()
            if iso_date != date_field["value"]:
                enriched["payment_date"] = {**date_field, "value": iso_date, "enriched": True}

    name_field = enriched.get("account_name", {})
    if name_field.get("value"):
        trimmed = str(name_field["value"]).strip()
        if trimmed != name_field["value"]:
            enriched["account_name"] = {**name_field, "value": trimmed, "enriched": True}

    _log_transition("enrichment_agent", state, "Parsed", "Enriched",
                    "OK", f"Enrichment complete for {doc_id}.")

    return {
        "ocr_fields": enriched,
        "document_state": "Enriched",
        "error": None,
        "messages": [AIMessage(
            content=f"[enrichment_agent] Enrichment complete for {doc_id}. "
                    f"Fields normalised and cross-referenced."
        )],
    }


# ---------------------------------------------------------------------------
# Node: build_spreadsheet (aggregates all enriched records into Excel)
# ---------------------------------------------------------------------------

def build_spreadsheet_node(state: ContraState) -> dict[str, Any]:
    """Aggregate all enriched file_records into a single Excel spreadsheet.

    Runs after enrichment and before matching/finalization.
    Writes the spreadsheet to the work directory.
    """
    from openpyxl import Workbook

    file_records: list[FileRecord] = list(state.get("file_records") or [])
    batch_id = state.get("batch_id") or state.get("document_id", "batch")
    settings = load_settings()

    # Determine output directory
    work_dir = Path(settings.work_directory) if settings.work_directory else Path(".")
    work_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = work_dir / f"{batch_id}_extracted_records.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Extracted Records"

    # Gather all field names across all records for dynamic columns
    all_field_names: list[str] = []
    seen: set[str] = set()
    for rec in file_records:
        for name in (rec.get("ocr_fields") or {}):
            if name not in seen:
                all_field_names.append(name)
                seen.add(name)

    # Header row
    headers = ["file_id", "source_file", "status"] + [
        f"{name}_value" for name in all_field_names
    ] + [
        f"{name}_confidence" for name in all_field_names
    ]
    ws.append(headers)

    # Data rows
    for rec in file_records:
        fields = rec.get("ocr_fields") or {}
        row: list[Any] = [
            rec.get("file_id", ""),
            Path(rec.get("source_path", "")).name if rec.get("source_path") else "",
            rec.get("status", ""),
        ]
        for name in all_field_names:
            row.append(fields.get(name, {}).get("value", ""))
        for name in all_field_names:
            row.append(fields.get(name, {}).get("confidence_score", ""))
        ws.append(row)

    # Auto-size columns (approximate)
    for col_cells in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col_cells), default=10)
        ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 2, 40)

    wb.save(str(xlsx_path))

    # --- Copy to review directory for human download ---
    review_dir_str = settings.review_directory
    review_spreadsheet_path = str(xlsx_path)
    if review_dir_str:
        review_dir = Path(review_dir_str)
        review_dir.mkdir(parents=True, exist_ok=True)
        review_dest = review_dir / xlsx_path.name
        shutil.copy2(str(xlsx_path), str(review_dest))
        review_spreadsheet_path = str(review_dest)

    _log_transition("spreadsheet_builder", state, "Enriched", "Spreadsheet_Built",
                    "OK", f"Spreadsheet with {len(file_records)} records written to {xlsx_path}.")

    # --- HITL: pause for human review of the spreadsheet ---
    human_input = interrupt({
        "reason": "Spreadsheet built — awaiting human review before matching.",
        "spreadsheet_path": review_spreadsheet_path,
        "record_count": len(file_records),
        "batch_id": batch_id,
    })

    # --- Human resumed: check for updated spreadsheet ---
    action = human_input.get("action", "approve")  # approve | upload
    reviewer_id = human_input.get("reviewer_id", "anonymous")
    rationale = human_input.get("rationale", "")
    uploaded_path = human_input.get("uploaded_path")

    if action == "reject":
        _log_transition("spreadsheet_builder", state, "Spreadsheet_Built", "Error_Queue",
                        "REJECTED", f"Reviewer {reviewer_id}: {rationale}")
        return {
            "spreadsheet_path": str(xlsx_path),
            "review_spreadsheet_path": review_spreadsheet_path,
            "document_state": "Error_Queue",
            "error": f"Spreadsheet rejected by {reviewer_id}: {rationale}",
            "human_review_action": "reject",
            "human_reviewer_id": reviewer_id,
            "human_review_rationale": rationale,
            "messages": [AIMessage(
                content=f"[spreadsheet_builder] Spreadsheet rejected by {reviewer_id}. {rationale}"
            )],
        }

    # If human uploaded a corrected spreadsheet, use that path
    final_spreadsheet = uploaded_path if uploaded_path else review_spreadsheet_path

    _log_transition("spreadsheet_builder", state, "Spreadsheet_Built", "Spreadsheet_Approved",
                    action.upper(), f"Reviewer {reviewer_id}: {rationale or 'Approved'}")

    return {
        "spreadsheet_path": str(xlsx_path),
        "review_spreadsheet_path": final_spreadsheet,
        "document_state": "Spreadsheet_Approved",
        "error": None,
        "human_review_action": action,
        "human_reviewer_id": reviewer_id,
        "human_review_rationale": rationale,
        "messages": [AIMessage(
            content=f"[spreadsheet_builder] Spreadsheet {action}d by {reviewer_id}. "
                    f"Proceeding to matching with {final_spreadsheet}."
        )],
    }


# ---------------------------------------------------------------------------
# Node: pii_redact
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def pii_redact_node(state: ContraState) -> dict[str, Any]:
    """Redact PII from document fields. Non-bypassable gate."""
    source_email = state.get("source_email", "")
    raw_text = state.get("raw_text")

    redacted_email = "[REDACTED]" if source_email else ""

    # Verify redaction succeeded
    if redacted_email and "@" in redacted_email:
        _log_transition("ingestion_agent", state, "Parsed", "Error_Queue",
                        "ERROR", "PII redaction failed — email still contains @.")
        return {
            "document_state": "Error_Queue",
            "error": "PII redaction failed.",
            "messages": [AIMessage(content="[pii_redaction] ERROR — redaction check failed.")],
        }

    _log_transition("ingestion_agent", state, "Parsed", "PII_Redacted",
                    "OK", "PII redacted. Email masked, raw text cleared.")

    return {
        "source_email": redacted_email,
        "raw_text": None,
        "document_state": "PII_Redacted",
        "error": None,
        "messages": [AIMessage(
            content="[pii_redaction] PII redacted — email masked to [REDACTED], raw text cleared."
        )],
    }


# ---------------------------------------------------------------------------
# Node: match
# ---------------------------------------------------------------------------

def match_node(state: ContraState) -> dict[str, Any]:
    """Match document against bank transaction candidates.

    Implements the full Auditor Agent constitution protocol:
    temporal window → zero variance → duplicate lock → bank ref ID → name similarity.
    """
    ocr_fields = state.get("ocr_fields", {})
    candidates = state.get("bank_candidates", [])
    doc_id = state.get("document_id", "")

    email_amount = float(ocr_fields.get("amount", {}).get("value") or 0)
    email_date_str = ocr_fields.get("payment_date", {}).get("value")
    email_date = _parse_date(email_date_str)
    email_ref = ocr_fields.get("bank_reference_id", {}).get("value")

    viable = []
    for txn in candidates:
        # Temporal window
        if email_date is not None:
            txn_date = _parse_date(txn.get("date"))
            if txn_date and abs((txn_date - email_date).days) > TEMPORAL_WINDOW_DAYS:
                continue
        # Zero variance
        if txn.get("amount", 0.0) - email_amount != 0.0:
            continue
        viable.append(txn)

    # Duplicate Lock
    if len(viable) > 1:
        ids = ", ".join(t.get("transaction_id", "?") for t in viable)
        result = {
            "match_id": str(uuid.uuid4()),
            "document_id": doc_id,
            "decision": "LOCKED",
            "amount_delta": 0.0,
            "rationale": f"Duplicate candidates ({ids}). Both LOCKED — human review required.",
        }
        _log_transition("auditor_agent", state, "PII_Redacted", "Human_Review",
                        "LOCKED", result["rationale"])
        return {
            "document_state": "Human_Review",
            "match_result": result,
            "error": None,
            "messages": [AIMessage(content=f"[auditor_agent] LOCKED — duplicates: {ids}")],
        }

    if not viable:
        result = {
            "match_id": str(uuid.uuid4()),
            "document_id": doc_id,
            "decision": "PENDING",
            "amount_delta": email_amount,
            "rationale": "No matching bank transaction found. Status: Pending.",
        }
        _log_transition("auditor_agent", state, "PII_Redacted", "Pending",
                        "PENDING", result["rationale"])
        return {
            "document_state": "Exception_Review",
            "match_result": result,
            "error": None,
            "messages": [AIMessage(content="[auditor_agent] No match found — PENDING.")],
        }

    txn = viable[0]
    txn_date = _parse_date(txn.get("date"))
    delta_days = abs((txn_date - email_date).days) if txn_date and email_date else None

    # Bank Reference ID supremacy
    if email_ref and txn.get("reference_id") and email_ref == txn["reference_id"]:
        result = {
            "match_id": str(uuid.uuid4()),
            "document_id": doc_id,
            "bank_transaction_id": txn["transaction_id"],
            "decision": "MATCHED",
            "amount_delta": 0.0,
            "bank_reference_id_match": True,
            "temporal_delta_days": delta_days,
            "rationale": f"Bank Ref ID '{email_ref}' matched exactly.",
        }
        _log_transition("auditor_agent", state, "PII_Redacted", "Matched",
                        "MATCHED", result["rationale"])
        return {
            "document_state": "Matched",
            "match_result": result,
            "error": None,
            "messages": [AIMessage(
                content=f"[auditor_agent] MATCHED via Bank Ref ID '{email_ref}'. Delta $0.00."
            )],
        }

    # Name similarity (Levenshtein)
    doc_name = (ocr_fields.get("account_name", {}).get("value") or "").lower()
    txn_name = (txn.get("account_name") or "").lower()
    score = levenshtein_ratio(doc_name, txn_name)

    if score < NAME_SIMILARITY_THRESHOLD:
        result = {
            "match_id": str(uuid.uuid4()),
            "document_id": doc_id,
            "bank_transaction_id": txn["transaction_id"],
            "decision": "FLAGGED",
            "amount_delta": 0.0,
            "name_similarity": round(score, 4),
            "temporal_delta_days": delta_days,
            "rationale": f"Name similarity {score:.4f} below threshold {NAME_SIMILARITY_THRESHOLD}.",
        }
        _log_transition("auditor_agent", state, "PII_Redacted", "Exception_Review",
                        "FLAGGED", result["rationale"])
        return {
            "document_state": "Exception_Review",
            "match_result": result,
            "error": None,
            "messages": [AIMessage(
                content=f"[auditor_agent] FLAGGED — name sim {score:.4f} < {NAME_SIMILARITY_THRESHOLD}"
            )],
        }

    result = {
        "match_id": str(uuid.uuid4()),
        "document_id": doc_id,
        "bank_transaction_id": txn["transaction_id"],
        "decision": "MATCHED",
        "amount_delta": 0.0,
        "name_similarity": round(score, 4),
        "temporal_delta_days": delta_days,
        "rationale": f"Amount $0.00 delta, name similarity {score:.4f}, within {delta_days}-day window.",
    }
    _log_transition("auditor_agent", state, "PII_Redacted", "Matched",
                    "MATCHED", result["rationale"])
    return {
        "document_state": "Matched",
        "match_result": result,
        "error": None,
        "messages": [AIMessage(
            content=f"[auditor_agent] MATCHED — name sim {score:.4f}, delta $0.00, {delta_days}d window."
        )],
    }


# ---------------------------------------------------------------------------
# Node: finalize
# ---------------------------------------------------------------------------

def finalize_node(state: ContraState) -> dict[str, Any]:
    """Generate receipt and mark as Finalized."""
    doc_id = state.get("document_id", "")

    _log_transition("finalization_agent", state, "Matched", "Finalized",
                    "OK", f"Receipt generated for {doc_id}. Pipeline complete.")

    return {
        "document_state": "Finalized",
        "error": None,
        "messages": [AIMessage(
            content=f"[finalization] Receipt generated for {doc_id}. Pipeline complete."
        )],
    }


# ---------------------------------------------------------------------------
# Node: error_handler (terminal)
# ---------------------------------------------------------------------------

def error_handler_node(state: ContraState) -> dict[str, Any]:
    """Terminal node for documents routed to error states."""
    error = state.get("error", "Unknown error")
    doc_state = state.get("document_state", "Error_Queue")
    return {
        "messages": [AIMessage(
            content=f"[error_handler] Document halted in {doc_state}: {error}"
        )],
    }


# ---------------------------------------------------------------------------
# Node: human_review (HITL interrupt)
# ---------------------------------------------------------------------------

def human_review_node(state: ContraState) -> dict[str, Any]:
    """Pause execution via LangGraph interrupt() for human review.

    The graph suspends here. When resumed with a Command, the human_review_*
    fields are populated in state, and the graph continues to the next node.
    """
    doc_id = state.get("document_id", "")
    doc_state = state.get("document_state", "")
    error = state.get("error", "")
    match_result = state.get("match_result")

    review_context = {
        "document_id": doc_id,
        "document_state": doc_state,
        "reason": error or (match_result or {}).get("rationale", "Review required"),
        "match_result": match_result,
    }

    # This suspends the graph and waits for human input
    human_input = interrupt(review_context)

    # When resumed, human_input contains the reviewer's decision
    reviewer_id = human_input.get("reviewer_id", "anonymous")
    action = human_input.get("action", "reject")  # approve | reject | correct
    rationale = human_input.get("rationale", "")
    corrected_data = human_input.get("corrected_data")

    _log_transition("human_reviewer", state, doc_state, f"HITL_{action}",
                    action.upper(), f"Reviewer {reviewer_id}: {rationale}")

    update: dict[str, Any] = {
        "human_review_action": action,
        "human_reviewer_id": reviewer_id,
        "human_review_rationale": rationale,
        "messages": [AIMessage(
            content=f"[human_review] Reviewer {reviewer_id} action: {action}. {rationale}"
        )],
    }

    if action == "approve":
        # Re-enter the pipeline at the appropriate point
        if doc_state == "Needs_Review":
            update["document_state"] = "Parsed"
            update["error"] = None
        elif doc_state == "Human_Review":
            update["document_state"] = "Matched"
            update["error"] = None
            if match_result:
                match_result["decision"] = "MATCHED"
                update["match_result"] = match_result
        elif doc_state == "Exception_Review":
            update["document_state"] = "Matched"
            update["error"] = None
    elif action == "correct" and corrected_data:
        # Human corrected OCR fields — retry OCR gate
        update["ocr_fields"] = corrected_data.get("ocr_fields", state.get("ocr_fields", {}))
        update["document_state"] = "Ingested"  # re-run OCR check
        update["error"] = None
    else:
        # Rejected — stay in error state
        update["document_state"] = "Error_Queue"
        update["error"] = f"Rejected by reviewer {reviewer_id}: {rationale}"

    return update


# ---------------------------------------------------------------------------
# Routing functions (conditional edges)
# ---------------------------------------------------------------------------

def route_after_ocr(state: ContraState) -> str:
    """Route after OCR extraction based on document state."""
    doc_state = state.get("document_state", "")
    if doc_state == "Parsed":
        return "enrich"
    elif doc_state == "Needs_Review":
        return "human_review"
    else:
        return "error_handler"


def route_after_match(state: ContraState) -> str:
    """Route after matching based on match decision."""
    doc_state = state.get("document_state", "")
    if doc_state == "Matched":
        return "finalize"
    elif doc_state == "Human_Review":
        return "human_review"
    elif doc_state == "Exception_Review":
        return "human_review"
    else:
        return "error_handler"


def route_after_human_review(state: ContraState) -> str:
    """Route after human review based on the reviewer's action."""
    action = state.get("human_review_action", "reject")
    doc_state = state.get("document_state", "")

    if action == "reject":
        return "error_handler"
    elif doc_state == "Ingested":
        # Corrected OCR fields — re-run OCR check
        return "ocr_extract"
    elif doc_state in ("Parsed", "Enriched"):
        return "enrich"
    elif doc_state == "Matched":
        return "finalize"
    else:
        return "error_handler"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    from datetime import datetime as dt
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return dt.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _log_transition(
    agent: str,
    state: ContraState,
    state_from: str,
    state_to: str,
    decision: str,
    rationale: str,
) -> None:
    """Write audit log entry for a state transition."""
    entry = AuditEntry(
        agent=agent,
        input_hash=compute_hash({
            "document_id": state.get("document_id"),
            "document_state": state.get("document_state"),
        }),
        output_hash=compute_hash({"state_to": state_to}),
        state_from=state_from,
        state_to=state_to,
        decision=decision,
        rationale=rationale,
        confidence_scores={
            name: field.get("confidence_score", 0.0)
            for name, field in state.get("ocr_fields", {}).items()
        },
    )
    audit_log.append(entry)

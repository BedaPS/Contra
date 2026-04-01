# Implementation Plan: Multi-Agent Document Processing System

**Branch**: `001-multi-agent-doc-processing` | **Date**: 2026-03-25 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/001-multi-agent-doc-processing/spec.md`

---

## Summary

Build a new LangGraph-based vision extraction pipeline that reads image-only documents from a configured source folder, classifies each document type, extracts 14 payment fields via a pluggable vision LLM, normalises and validates the output, then writes a colour-coded Excel file and JSON accuracy log. The system is triggered from the existing Angular UI via `POST /api/runs` and streams real-time per-file progress via AG-UI protocol SSE events. All data is persisted to three new MSSQL tables (`batch_runs`, `run_records`, `payment_records`). The pipeline runs in a separate LangGraph `StateGraph` from the existing reconciliation pipeline, with full constitution compliance on audit logging, LLM adapter boundary, and API contract.

---

## Technical Context

**Language/Version**: Python 3.12+ (backend), TypeScript strict / Angular 21 (frontend)  
**Primary Dependencies**:
- Backend: FastAPI 0.135.2, LangGraph 1.1.3, LangChain-core 1.2.20, SQLAlchemy 2.0.48, openpyxl 3.1.5 (existing); PyMuPDF 1.26.1, Pillow 11.2.1, PyYAML 6.0.2 (new)
- Frontend: Angular 21.2.5, RxJS 7.8.2, @ag-ui/core 0.0.47 (existing)

**Storage**: MSSQL 2022 via pymssql 2.3.13 — three new tables added via Alembic migration  
**Testing**: pytest 8.4.1 (backend), Angular Jasmine/Karma (frontend)  
**Target Platform**: Docker Compose (Linux containers) + Angular dev server  
**Project Type**: Web service (FastAPI backend + Angular frontend)  
**Performance Goals**: Process a folder of 10 documents end-to-end without manual intervention (SC-001)  
**Constraints**: Zero code changes for LLM provider swap (SC-002); zero code changes for new doc type (SC-003); graph inspectable via Mermaid (SC-008)  
**Scale/Scope**: Per-run batch processing (no concurrency between runs); one active run at a time

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Gate | Requirement | Status |
|---|------|-------------|--------|
| G1 | Zero Variance | Amount delta logic produces exactly $0.00 or routes to `Exception_Review` | [x] N/A — this pipeline does not perform bank matching. No amount deltas are computed. The feature extracts and validates amounts from documents; reconciliation is the existing pipeline's responsibility. |
| G2 | Source of Truth | Bank Reference ID evaluated first; email-only claims marked `Pending`, never `Paid` | [x] N/A — no matching or payment status decisions are made. Output status values are `Valid` / `Review Required` / `Extraction Failed` — not `Paid` / `Pending`. |
| G3 | Privacy Mandate | Ingestion Agent redacts PII before any downstream pass; no raw PII in payloads or logs | [x] `account_number` is extracted and stored in `payment_records` (it is a desired output — the purpose of this pipeline is to capture payment fields from documents, of which `account_number` is one). **Approved exception**: storing `account_number` in the `payment_records` DB table and returning it in API responses and Excel output is intentional by design, not incidental PII exposure. It MUST NOT appear in audit log entries (see §G7). Audit log entries contain only field names and confidence scores — no field values. All audit log entries mask `account_number` as `****<last-4>`. No further DB-level masking is required for this column. The `account_number` value shown as `****4321` in `contracts/openapi-additions.md` is sample data from a document that already contained a masked number — the API serialiser does NOT mask `account_number` during response serialisation; raw extracted values are returned as-is. |
| G4 | Vision Agent | Every OCR field emits `confidence_score`; fields `< 0.85` flagged `NEEDS_REVIEW` | [x] Every extracted field carries a `confidence_score` (0.0–1.0) in `DocPipelineState.raw_records`. This pipeline uses a **two-tier per-field YAML threshold** approach: **(1) Match-critical fields** — `amount_paid` ≥ 0.90 (above the constitution's 0.85 spirit for the most impactful field), `payment_date` ≥ 0.80 and `account_number` ≥ 0.80 (near threshold; low confidence routes record to `Review Required`); **(2) Informational fields** — `notes`, `deduction_type`, `payment_id`, `invoice_number`, etc. at ≥ 0.70 (these do not affect matching decisions; low confidence still produces `Review Required` status — a STRICTER outcome than the constitution's soft `NEEDS_REVIEW` flag, as the record's bad status is permanent and visible in UI and Excel output). The blanket 0.85 applies only to the existing reconciliation pipeline. (See research.md §Decision 11.) |
| G5 | Auditor Agent | Name similarity threshold ≥ 0.90 (Levenshtein); 7-day temporal window enforced; Duplicate Lock rule implemented | [x] N/A — no bank matching in this feature. |
| G6 | State Machine | All five states (`Ingested → Parsed → PII_Redacted → Matched → Finalized`) gate-checked and atomic | [x] New pipeline uses its own graph: `classifier_node → extractor_node → normaliser_node → validator_node → excel_writer_node`. Conditional edges enforce gate checks between nodes. Error routing to terminal node on failures. No modification to the existing reconciliation `ContraState` or graph. |
| G7 | Audit Trail | Every agent writes a reasoning log entry before completing any state transition | [x] Each of the five new nodes writes to `AuditLogModel` via `audit_log.append()` before returning its state update. Audit entries contain: `agent`, `timestamp`, `input_hash`, `output_hash`, `state_from`, `state_to`, `decision`, `rationale`, `confidence_scores`. No PII field values in entries. |
| G8 | LLM Adapter | All LLM calls routed through `llm_adapter.py`; no vendor SDK calls outside the adapter layer | [x] New `LLMAdapter.invoke_vision(prompt, images)` method handles multimodal calls. All classification and extraction calls go through this method. No vendor SDKs imported in `doc_pipeline/nodes.py`. |
| G9 | API Contract | Frontend consumes only OpenAPI-generated DTOs; no hand-written duplicate type interfaces | [x] `RunsService` (which includes `getResults()`) in Angular calls only FastAPI endpoints. TypeScript interfaces in `run.models.ts` are hand-written NOW (during development), but the plan documents that `npm run generate:api` will replace them at the end of the implementation phase. The `generated/` folder remains the authoritative contract. |

*All gates checked. G1, G2, G5 are N/A for this pipeline. G3, G4, G7 have documented justifications. All others fully compliant.*

---

## Project Structure

### Documentation (this feature)

```text
specs/001-multi-agent-doc-processing/
├── plan.md              ← This file
├── spec.md              ← Source of truth (status: Clarified)
├── research.md          ← Phase 0 research decisions
├── data-model.md        ← Entity schemas, state transitions
├── quickstart.md        ← End-to-end developer setup guide
├── contracts/
│   └── openapi-additions.md   ← API contract for all new endpoints
└── tasks.md             ← Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code Changes

```text
backend/
├── src/
│   ├── graph/
│   │   └── doc_pipeline/          ← NEW
│   │       ├── __init__.py
│   │       ├── state.py            ← DocPipelineState TypedDict + PaymentRecordDict
│   │       ├── nodes.py            ← 5 node functions (classifier, extractor,
│   │       │                          normaliser, validator, excel_writer)
│   │       └── pipeline.py         ← StateGraph with 5 nodes + error routing
│   ├── db/
│   │   └── models.py               ← MODIFY: add BatchRunModel, RunRecordModel,
│   │                                    PaymentRecordModel
│   ├── schemas/
│   │   ├── payment_record.py       ← NEW: PaymentRecordCreate, PaymentRecordResponse
│   │   ├── run.py                  ← NEW: RunStartedResponse, BatchRunSummary,
│   │   │                                  BatchRunDetail, RunRecordSummary
│   │   └── llm_settings.py         ← MODIFY: add output_directory field
│   ├── adapters/
│   │   └── llm_adapter.py          ← MODIFY: add invoke_vision() multimodal method
│   ├── services/
│   │   └── run_service.py          ← NEW: BatchRun/RunRecord CRUD + async orchestration
│   ├── prompt_configs/             ← NEW
│   │   ├── email.yaml
│   │   ├── remittance.yaml
│   │   ├── receipt.yaml
│   │   └── unknown.yaml
│   ├── api/
│   │   └── routes.py               ← MODIFY: add /runs, /results + SSE stream endpoints
│   └── settings_store.py           ← MODIFY: add OUTPUT_DIRECTORY env var
├── alembic/
│   └── versions/
│       └── XXXX_add_doc_processing_tables.py   ← NEW Alembic migration
└── requirements.txt                ← MODIFY: add pymupdf, Pillow, PyYAML

frontend/
├── src/
│   ├── app/
│   │   ├── core/
│   │   │   ├── models/
│   │   │   │   ├── ag-ui.models.ts        ← MODIFY: new batch event interfaces
│   │   │   │   └── run.models.ts          ← NEW: BatchRun, RunRecord, PaymentRecord TS types
│   │   │   └── services/
│   │   │       ├── ag-ui-event.service.ts ← MODIFY: connectToBatch(), handle new events
│   │   │       └── runs.service.ts        ← NEW: HTTP calls to /runs, /results
│   │   ├── features/
│   │   │   ├── runs/                      ← NEW (standalone component)
│   │   │   │   └── runs.component.ts      ← Run history list + Run Pipeline button
│   │   │   │                                  + live progress indicator
│   │   │   └── results/                   ← NEW (standalone component)
│   │   │       └── results.component.ts   ← Filterable PaymentRecord table
│   │   ├── app.routes.ts                  ← MODIFY: add /runs, /results routes
│   │   └── shared/shell/
│   │       └── shell.component.ts         ← MODIFY: add "Run History" + "Results" nav links
```

**Structure Decision**: Web application layout (Option 2 from template). The existing `backend/` and `frontend/` split is preserved. The new doc pipeline code is isolated in `backend/src/graph/doc_pipeline/` to avoid coupling with the existing `backend/src/graph/` reconciliation pipeline.

---

## Architecture: New LangGraph Pipeline

### Graph Topology

```
POST /api/runs
    │
    ▼
[classifier_node]
  - Load page 1 image via PyMuPDF
  - Call LLMAdapter.invoke_vision(classify_prompt, [page_1_image])
  - Parse: doc_type ∈ {email, remittance, receipt, unknown}
  - Load prompt_config from YAML (cached)
  - Gate: if classify fails → error_node
    │
    ▼
[extractor_node]
  - Render all pages to base64 PNG (PyMuPDF)
  - Resize if > 20 MB (Pillow)
  - For each page: call LLMAdapter.invoke_vision(extract_prompt, [page_image])
  - Parse JSON → list[PaymentRecordDict] (one per distinct amount)
  - Retry on parse failure (max 3 attempts)
  - Gate: all-null → error_node; 3 parse failures → error_node
    │
    ▼
[normaliser_node]
  - Dates → YYYY-MM-DD (dateutil.parse or regex)
  - Amounts → float (strip currency symbols, commas)
  - Currencies → ISO 4217 (lookup table)
  - Payment methods → canonical form (EFT, CASH, CHEQUE, ...)
  - No LLM calls
    │
    ▼
[validator_node]
  - Load per-field YAML thresholds from prompt_config
  - Per record, per field: compare confidence_score vs. threshold
  - Assign validation_status:
    1. 'Extraction Failed' if amount_paid null OR confidence_score < threshold
    2. 'Review Required' if any other field below its threshold
    3. 'Valid'
  - No LLM calls
    │
    ▼
[excel_writer_node]
  - Audit log entry (FIRST — constitution G7)
  - DB: INSERT INTO payment_records (batch insert all validated_records)
  - DB: UPDATE run_records SET status='Completed', record_count=N, completed_at=now()
  - DB: UPDATE batch_runs SET total_records=total_records+N
  - Move failed files → {work_dir}/failed/
  - Append to {output_dir}/accuracy.jsonl
  - Rewrite {output_dir}/results.xlsx (all existing + new records for batch_id)
    │
    ▼
   END (per file)
```

### Error Node

All nodes route to `error_node` on unrecoverable errors:
- Classifier failure → `error_node`
- 3 extraction parse failures → `error_node`
- All-null extraction → `error_node`

`error_node` writes audit entry, sets `RunRecord.status = 'Failed'`, moves source file to `{work_dir}/failed/`, emits `FILE_FAILED` AG-UI event.

### Async Batch Orchestration (run_service.py)

```
POST /api/runs
  → Create BatchRun (In Progress) in DB
  → Scan source_dir for supported files
  → Create RunRecord per file (Pending) in DB
  → Register asyncio.Queue for batch_id in _run_queues dict
  → asyncio.create_task(process_batch(...))
  → Return RunStartedResponse immediately

process_batch():
  → emit BATCH_STARTED event to queue
  → for each file (sequential):
      emit FILE_STARTED
      create DocPipelineState
      run_graph = get_doc_pipeline()
      result = run_graph.invoke(initial_state)
      emit FILE_COMPLETED or FILE_FAILED based on result
  → Update BatchRun.status, completed_at
  → emit BATCH_COMPLETED
  → remove queue from _run_queues

GET /api/runs/{batch_id}/stream
  → StreamingResponse(generate_sse(batch_id))
  → generate_sse drains queue and yields SSE frames
  → Closes when BATCH_COMPLETED received
```

---

## Sequence Diagrams

### Happy Path (single file)

```
UI             FastAPI          run_service      LangGraph            DB
 │                │                 │                │                │
 │ POST /runs     │                 │                │                │
 │──────────────►│                 │                │                │
 │               │ create BatchRun │                │                │
 │               │────────────────►│ INSERT batch_runs               │
 │               │                 │────────────────────────────────►│
 │               │ scan source dir │                │                │
 │               │────────────────►│                │                │
 │               │ create RunRecord│                │                │
 │               │────────────────►│ INSERT run_records              │
 │               │                 │────────────────────────────────►│
 │ {batch_id}    │                 │ create_task(process_batch)      │
 │◄──────────────│                 │                │                │
 │ EventSource   │                 │                │                │
 │──────────────►│                 │                │                │
 │               │                 │ BATCH_STARTED  │                │
 │◄─ SSE ────────│◄────────────────│                │                │
 │               │                 │ FILE_STARTED   │                │
 │◄─ SSE ────────│◄────────────────│                │                │
 │               │                 │ graph.invoke() │                │
 │               │                 │───────────────►│                │
 │               │                 │                │ LLM classify   │
 │               │                 │                │ LLM extract    │
 │               │                 │                │ normalise      │
 │               │                 │                │ validate       │
 │               │                 │◄───────────────│ INSERT records │
 │               │                 │                │───────────────►│
 │               │                 │ FILE_COMPLETED │                │
 │◄─ SSE ────────│◄────────────────│                │                │
 │               │                 │ BATCH_COMPLETED│                │
 │◄─ SSE ────────│◄────────────────│                │                │
```

### Error Path (extraction failure)

```
                 process_batch    LangGraph
                      │               │
                      │ graph.invoke() │
                      │───────────────►
                      │               │ LLM extract → 3 parse failures
                      │               │ → error_node
                      │               │ UPDATE run_records status='Failed'
                      │               │ move file → failed/
                      │◄──────────────│ return {error: ..., error_type: 'parse_error'}
                      │
                      │ emit FILE_FAILED event
                      │ continue to next file
```

---

## Angular UI Component Plan

### `RunsComponent` (`/runs`) — New Feature

**Responsibilities**:
- Displays "Run Pipeline" button
- Shows run history list (createdAt, status chip, total_files, total_records)
- Shows live progress for active run: `N of M files processed` via AG-UI SSE
- Clicking a completed run navigates to `/results?batch_id=<id>`

**Signals used**:
- `AgUiEventService.isRunning` — disable button while running
- Local `runs` signal from `RunsService.listRuns()`
- Local `progress` signal updated on `FILE_COMPLETED` / `FILE_FAILED` events

### `ResultsComponent` (`/results`) — New Feature

**Responsibilities**:
- Reads `batch_id` from query params
- Loads `PaymentRecord[]` from `RunsService.getResults({batch_id})`
- Table columns: Customer, Amount, Currency, Payment Date, Status, Confidence, Model, Source File
- Row colour: green/amber/red based on `validation_status`
- Filter panel: `validation_status`, `doc_type`, confidence range
- Expand row → per-field confidence breakdown

**No Angular Material** — custom CSS consistent with existing shell (dark theme).

---

## Prompt Config Design

Each YAML file in `backend/src/prompt_configs/` has this structure:

```yaml
context_hint: |
  This document is a [type] payment document. Extract all 14 fields precisely.
  Return ONLY valid JSON. No prose. The JSON must conform to the extraction schema.

field_hints:
  customer_name: "Full name of the payer as printed."
  account_number: "Bank account number. Include all digits exactly as shown."
  payee: "Name of the payment recipient / payee."
  payment_id: "Any unique transaction or payment reference ID."
  payment_method: "Payment method: EFT, CASH, CHEQUE, DIRECT_DEPOSIT, or CARD."
  payment_date: "Payment date in any format. Will be normalised to YYYY-MM-DD."
  invoice_number: "Invoice or document number referenced."
  reference_doc_number: "Additional reference document number if present."
  amount_paid: "Total payment amount as a numeric value. CRITICAL — must not be null."
  currency: "ISO 4217 currency code or symbol."
  deductions: "Any deductions or adjustments in numeric value."
  deduction_type: "Reason or type for any deductions."
  notes: "Any additional notes or remarks on the document."

confidence_thresholds:
  customer_name: 0.75
  account_number: 0.80
  payee: 0.75
  payment_id: 0.70
  payment_method: 0.75
  payment_date: 0.80
  invoice_number: 0.70
  reference_doc_number: 0.70
  amount_paid: 0.90     # Must be >= 0.85 — see research.md §Decision 11
  currency: 0.75
  deductions: 0.70
  deduction_type: 0.70
  notes: 0.70

required_fields:
  - amount_paid
```

The classifier prompt is embedded in `classifier_node` (not YAML) as it is doc-type-agnostic.

---

## LLM Adapter Extension

`LLMAdapter.invoke_vision(prompt: str, images: list[str]) -> str`

```python
def invoke_vision(self, prompt: str, images: list[str]) -> str:
    """Invoke the vision model with a text prompt and base64 image list.
    
    Returns raw string response (JSON expected by caller).
    Raises LLMInvokeError on failure.
    """
    from langchain_core.messages import HumanMessage
    
    content: list[dict] = [{"type": "text", "text": prompt}]
    for b64 in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"}
        })
    
    message = HumanMessage(content=content)
    response = self.model.invoke([message])
    return response.content
```

---

## New Dependencies

Add to `backend/requirements.txt`:

```
pymupdf==1.26.1
Pillow==11.2.1
PyYAML==6.0.2
```

No new frontend dependencies required.

---

## Alembic Migration

New revision file: `backend/alembic/versions/{rev}_add_doc_processing_tables.py`

Creates (in order, due to FK constraints):
1. `batch_runs` table
2. `run_records` table (FK → `batch_runs.batch_id`)
3. `payment_records` table (FK → `run_records.record_id`)

All indexes as documented in `data-model.md §1`.

MSSQL FK note: `pymssql` does not support `ON DELETE CASCADE` on all FK types — FK constraints are set without cascade; orphan cleanup is handled at application level.

---

## Testing Plan

### Unit Tests (new)
- `tests/unit/test_normaliser.py` — one test per normalisation rule (date, amount, currency, payment_method) — required by SC-006
- `tests/unit/test_validator.py` — test each validation_status branch with mock confidence scores
- `tests/unit/test_classifier.py` — mock `LLMAdapter.invoke_vision()`, assert each `doc_type` parsed correctly, assert `error_node` routing on failure (T047)
- `tests/unit/test_extractor.py` — test retry logic, all-null detection, `page_number` tagging, 429 backoff (T048, T049)
- `tests/unit/test_doc_pipeline_state.py` — verify state TypedDict structure (T014)

### Integration Tests (new)
- `tests/integration/test_doc_pipeline.py` — full graph invocation with a stub LLM returning canned JSON; verify all DB records created
- `tests/integration/test_runs_api.py` — `POST /api/runs`, `GET /api/runs`, `GET /api/results` with test DB

### Contract Tests (existing, extend)
- `tests/contract/test_health.py` — no change
- Add basic smoke check for `/api/v1/runs` endpoint existence

---

## Complexity Tracking

*No Constitution Check violations requiring justification.*

The context-specific threshold handling (G4 override) is a justified extension documented in `research.md §Decision 11`, not a complexity violation.

---

## Post-Design Constitution Re-check

All nine gates re-evaluated after Phase 1 design:

- **G3 (Privacy)**: `account_number` appears in `PaymentRecordModel` and API responses — this is intentional extraction output (approved exception; see G3 gate above). In audit log entries, `account_number` value is NEVER written — only the confidence score is logged: `{"account_number": 0.87}`. In the `accuracy.jsonl` file, no field values are written (only counts and scores). `excel_writer_node` MUST NOT write raw `account_number` to audit entries. ✅
- **G7 (Audit Trail)**: Confirmed — each of the 5 nodes writes an `AuditLogModel` entry before returning. The `excel_writer_node` writes its audit entry before the DB batch insert and file writes. ✅
- **G8 (LLM Adapter)**: `classifier_node` and `extractor_node` call `LLMAdapter.invoke_vision()`. No `langchain_openai`, `langchain_anthropic`, or `langchain_google_genai` imports in `doc_pipeline/nodes.py`. ✅
- **G9 (API Contract)**: `runs.service.ts` is the service layer. Angular components use `RunsService`, not raw `HttpClient`. After implementation, `npm run generate:api` produces `frontend/src/generated/` DTOs. ✅

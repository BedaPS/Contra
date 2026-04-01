# Feature Specification: Multi-Agent Document Processing System

**Feature Branch**: `001-multi-agent-doc-processing`  
**Created**: 2026-03-25  
**Status**: Clarified  
**Input**: User description: "Multi-Agent Document Processing System: LangGraph pipeline for image-only documents with vision LLM extraction, Excel output, and Angular frontend"

## Clarifications

### Session 2026-03-25

- Q: How is the pipeline triggered — CLI batch, auto-trigger on upload, or polling model? → A: Pipeline is **triggered from the Angular UI** via a "Run Pipeline" button (`POST /api/runs`). The backend reads from the configured source folder. Source, work, and output folder paths are all configurable via application settings.
- Q: How should multiple `amount_paid` values across pages of a multi-page document be handled — summed, largest taken, or separate records? → A: Every distinct payment amount found in the document produces a **separate `PaymentRecord`**. There is no merging. One page = one record; one document with 5 amounts = 5 records.
- Q: When a YAML config defines confidence thresholds, which governs the `Review Required` / `Valid` decision? → A: **Per-field thresholds defined in YAML**. Each field in the YAML has its own minimum confidence threshold. The overall record `validation_status` is derived from the **worst-performing field**: if any field falls below its YAML threshold, the record is `Review Required`; if `amount_paid` is null or below threshold, it is `Extraction Failed`. No global override threshold.
- Q: How should the Angular UI receive real-time run progress updates — polling, SSE, or WebSocket? → A: **AG-UI protocol** (already used in this codebase via `ag-ui-event.service.ts` and `agent_events.py`). The backend emits structured AG-UI events as each file is processed; the Angular frontend subscribes via the existing `AgUiEventService` to update the run progress display in real time.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trigger Pipeline from UI and Get Excel Output (Priority: P1)

A finance operator opens the Angular web interface, clicks **Run Pipeline**, and the backend scans the configured source folder. The Classifier agent assigns each document a unique GUID, copies it to the configured work folder, creates a `BatchRun` record and individual `RunRecord` entries in the database, then passes each file through the full extraction pipeline. The system produces a colour-coded Excel file in the configured output folder with all records.

**Why this priority**: This is the core value proposition. Without this working, nothing else has meaning.

**Independent Test**: Configure source/work/output folder paths in settings, place 3–5 sample documents in the source folder, click Run Pipeline in the Angular UI, and verify the work folder contains GUID-named copies, the DB has a `BatchRun` + per-file `RunRecord` entries, and `results.xlsx` is produced in the output folder.

**Acceptance Scenarios**:

1. **Given** 5 mixed payment documents in the source folder, **When** the operator clicks Run Pipeline in the UI, **Then** each file is copied to the work folder with a unique GUID filename, a `BatchRun` and per-file `RunRecord` are created in the DB, and `results.xlsx` in the output folder contains one row **per extracted payment amount** with all 14 data columns plus Confidence Score, LLM Model, and Source File columns.
2. **Given** a 3-page PDF where each page contains a distinct payment amount, **When** processed, **Then** `results.xlsx` contains 3 separate rows — one per amount — each referencing the same Source File.
3. **Given** a document that cannot be parsed, **When** processed, **Then** the record appears as `Extraction Failed` in the Excel and the source file is moved to `failed/`.
4. **Given** `LLM_PROVIDER=openai` and `LLM_MODEL=gpt-4o` in `.env`, **When** the pipeline runs, **Then** it completes without any code changes.

---

### User Story 2 - View Run History and Filter Results in the Browser (Priority: P2)

A user opens the Angular web interface, sees a list of previous batch runs, selects a run, and browses the filterable results table for that run. They inspect per-field confidence scores and can trigger a new run via the Run Pipeline button.

**Why this priority**: Provides the primary UI for both triggering runs and reviewing extraction results without requiring CLI or direct file access.

**Independent Test**: Trigger a run via the UI with sample documents, refresh the run history view, select the completed run, and verify all processed records appear in the results table with correct statuses and confidence scores.

**Acceptance Scenarios**:

1. **Given** the user clicks Run Pipeline, **When** the backend accepts the request, **Then** a new `BatchRun` entry appears in the run history list with status `In Progress` and AG-UI events begin streaming file-level progress to the UI.
2. **Given** a file completes processing, **When** the AG-UI event is received, **Then** the UI increments the progress counter (e.g., "3 of 12 files processed") without any manual refresh.
3. **Given** a batch run has completed, **When** the user selects it in the run history, **Then** the results table shows all `PaymentRecord` rows for that run with status chips coloured green (Valid), amber (Review Required), or red (Extraction Failed).
4. **Given** multiple records in the table, **When** the user filters by `validation_status = Review Required`, **Then** only matching records are shown.
5. **Given** a record row is clicked, **When** the detail panel opens, **Then** per-field confidence scores are visible for every extracted field.

---

### User Story 3 - Monitor Accuracy and Compare LLM Providers (Priority: P3)

A developer or data analyst reviews the `accuracy.jsonl` log to compare extraction quality across different LLM providers and models over time, using the logged provider/model metadata.

**Why this priority**: Enables continuous improvement and provider cost/quality trade-off analysis.

**Independent Test**: Run the pipeline twice with different `LLM_PROVIDER` values and verify `accuracy.jsonl` contains separate entries with distinct `llm_provider` and `llm_model` fields.

**Acceptance Scenarios**:

1. **Given** the pipeline runs with `LLM_PROVIDER=anthropic`, **When** a record is processed, **Then** `accuracy.jsonl` contains an entry with `llm_provider: "anthropic"` and the configured model name.
2. **Given** a completed run, **When** `accuracy.jsonl` is read, **Then** each entry contains: timestamp, source_filename, doc_type, validation_status, overall_confidence, fields_extracted, null_fields, and extraction_attempts.

---

### Edge Cases

- What happens when the input folder is empty? Pipeline exits cleanly with "0 files processed" summary.
- What happens when a YAML prompt file is missing for a classified `doc_type`? Falls back to `unknown.yaml` and logs a warning.
- What happens when a page yields no extractable payment amount? That page produces one record with `amount_paid = null` and status `Extraction Failed`; other pages continue processing normally.
- What happens when all 14 extracted fields are null? Immediately set to `Extraction Failed` without retrying.
- What happens when the LLM API returns malformed JSON? Retry up to **3 total attempts** (1 initial + 2 retries). After 3 parse failures the record is marked `Extraction Failed`.
- What happens when a rate limit (HTTP 429) is returned? Exponential backoff: 5s → 15s → 45s, then fail.
- What happens when a file was already processed? Skip it if a `RunRecord` with that `source_filename` and status `Completed` already exists for the active batch (DB-based dedup — see research.md Decision 8).
- What happens when an image exceeds 20 MB? 20 MB is measured as the raw decoded pixel buffer size (not the base64-encoded string length). If the decoded buffer exceeds 20 MB, resize to ≤ 4096px on the longest side before base64 encoding.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST read source folder, work folder, and output folder paths from application settings (not hardcoded).
- **FR-002**: The Classifier agent MUST scan all supported files (`.pdf`, `.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif`, `.bmp`, `.webp`) from the configured source folder.
- **FR-003**: For each file found, the Classifier MUST assign a unique GUID, copy the file to the work folder under that GUID (e.g., `{guid}_{original_filename}`), and create a linked `RunRecord` under the active `BatchRun` before any further processing.
- **FR-003a**: See FR-015 for the complete endpoint list. This requirement emphasises the run-creation semantics specifically: calling `POST /api/v1/runs` creates a `BatchRun` record, scans the source folder, and begins async processing of all discovered files.
- **FR-004**: All document-to-image conversion MUST go through the vision LLM — no text extraction from PDFs is permitted.
- **FR-005**: The pipeline MUST classify each document as one of: `email`, `remittance`, `receipt`, or `unknown` before extraction.
- **FR-006**: The Extractor MUST produce **one `PaymentRecord` per distinct payment amount** found in a document. A multi-page document with N distinct amounts produces N records, all sharing the same `source_filename` and GUID. Distinct is keyed on `(amount_paid, page_number)` — the same dollar amount appearing on two different pages produces two separate records.
- **FR-006a**: Each `PaymentRecord` MUST contain exactly 14 fields: `customer_name`, `account_number`, `payee`, `payment_id`, `payment_method`, `payment_date`, `invoice_number`, `reference_doc_number`, `amount_paid`, `currency`, `deductions`, `deduction_type`, `notes`, and `validation_status`. `doc_type` and `page_number` are metadata fields stored alongside each record but are not counted as part of the 14 payment fields; `doc_type` is not rendered as a column in `results.xlsx`.
- **FR-007**: Every extracted field MUST carry a per-field confidence score (0.0–1.0). Each field is compared against its own threshold defined in the doc-type YAML config.
- **FR-007a**: The YAML `PromptConfig` for each doc type MUST define a `confidence_threshold` per field. Fields without an explicit threshold inherit a fallback default of `0.70`.
- **FR-008**: The pipeline MUST normalise dates to `YYYY-MM-DD`, amounts to `float`, and currencies to ISO 4217 codes.
- **FR-009**: The Validator MUST assign `validation_status` using these rules, in priority order:
  1. `Extraction Failed` — if `amount_paid` is null OR its confidence is below its YAML threshold.
  2. `Review Required` — if ANY other field's confidence is below its YAML threshold.
  3. `Valid` — all fields meet or exceed their YAML thresholds.
- **FR-010**: The pipeline MUST append one structured JSON entry to `output/accuracy.jsonl` after each document is processed.
- **FR-011**: The pipeline MUST produce `results.xlsx` in the configured output folder with two sheets: `Payment Records` (all) and `Review Required` (failures and reviews only).
- **FR-012**: Failed documents MUST be moved to a `failed/` subdirectory within the work folder.
- **FR-013**: The LLM provider MUST be swappable via environment variable (`LLM_PROVIDER`, `LLM_MODEL`) with zero code changes.
- **FR-014**: New document types MUST be addable by creating one YAML config file only — no code changes.
- **FR-015**: The FastAPI backend MUST expose: `POST /api/v1/runs` (trigger pipeline), `GET /api/v1/runs` (list all batch runs), `GET /api/v1/runs/{batch_id}` (run detail + file statuses), `GET /api/v1/results` (all payment records, filterable by batch ID), and `GET /api/v1/runs/{batch_id}/stream` (AG-UI SSE event stream for real-time per-file progress during an active run).
- **FR-016**: The Angular frontend MUST use the existing `AgUiEventService` to subscribe to run progress events and update the UI in real time. Components required: **Run Pipeline button**, **run history list**, **live progress indicator** (files processed / total), and **filterable results table** scoped to a selected run. No file upload UI is required.
- **FR-017**: The results table MUST support filtering by `doc_type`, `validation_status`, and confidence range.

### Key Entities

- **PipelineState**: The shared typed state object passed through all LangGraph nodes. Carries file metadata (including GUID and work folder path), page images (base64), a **list of extracted `PaymentRecord` items** (one per distinct amount found), confidence scores, normalised fields, validation outcomes, and error tracking.
- **BatchRun**: A DB record created when the UI triggers a pipeline run via `POST /api/runs`. Stores: batch ID (GUID), triggered timestamp, completion timestamp, total files found, total records produced, and overall status (`In Progress` / `Completed` / `Failed`). AG-UI events emitted during the run carry this batch ID so the frontend can correlate updates.
- **RunRecord**: A DB record created per file within a `BatchRun`. Stores: record ID (GUID), batch ID (FK), source filename, work folder path, GUID-prefixed work filename, start timestamp, completion timestamp, record count extracted, and final status.
- **PaymentRecord**: The 14-column output record. Represents one fully-processed document with all extracted payment fields plus metadata (validation status, confidence, LLM model, source file).
- **AccuracyLogEntry**: A JSONL line written per document. Records provider, model, confidence, null fields, extraction attempts, and validation outcome for monitoring and comparison.
- **PromptConfig**: A YAML file per document type defining the context hint, field hints, **per-field confidence thresholds** (with `0.70` as fallback), and required fields used by the Extractor and Validator nodes.
- **VisionLLMProvider**: The abstract interface all LLM adapters implement (`classify()` and `extract()` methods). Decouples pipeline nodes from vendor SDKs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Pipeline processes a folder of 10 mixed documents and produces a complete `results.xlsx` without manual intervention.
- **SC-002**: Swapping the LLM provider requires only a change to `.env` — zero lines of source code need modification.
- **SC-003**: A new document type can be supported by creating one YAML file — no node code changes required.
- **SC-004**: A 3-page PDF where each page contains a distinct payment amount produces exactly 3 separate records in `results.xlsx`, all with the same Source File value.
- **SC-005**: Each `accuracy.jsonl` entry contains `llm_provider` and `llm_model`, enabling cross-provider accuracy comparison.
- **SC-006**: Node 3 (Normaliser) has at least one unit test per normalisation rule (date, amount, currency, payment method).
- **SC-007**: The Angular results table loads all records and filters correctly by status and document type.
- **SC-008**: The LangGraph graph structure is inspectable via `graph.get_graph().draw_mermaid()` without errors.

## Assumptions

- All input PDFs are image-only (no embedded text layer). No text-extraction fallback is needed or desired.
- Document classification returns one of four fixed types. An `unknown` type uses permissive extraction settings.
- The `amount_paid` field is the single most critical field; its absence always results in `Extraction Failed`.
- Multi-page documents are NOT merged. Each distinct payment amount found (on any page) produces a separate `PaymentRecord`. Shared header fields (e.g., `customer_name`) are copied to every record from the same source file.
- The pipeline is triggered from the Angular UI via a **Run Pipeline** button — not from the CLI. There is no `python main.py` entry point for production use.
- Source, work, and output folder paths are configured in application settings (e.g., `.env` or a settings store) — not hardcoded.
- There is no drag-and-drop or browser upload flow; all document ingestion reads from the configured source folder on the server.

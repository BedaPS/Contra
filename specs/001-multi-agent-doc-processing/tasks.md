# Tasks: Multi-Agent Document Processing System

**Branch**: `001-multi-agent-doc-processing`  
**Generated**: 2026-03-31  
**Input**: `specs/001-multi-agent-doc-processing/plan.md`, `spec.md`, `data-model.md`, `contracts/openapi-additions.md`, `research.md`, `quickstart.md`

**User Stories**:
- **US1** (P1): Trigger Pipeline from UI and Get Excel Output
- **US2** (P2): View Run History and Filter Results in the Browser
- **US3** (P3): Monitor Accuracy and Compare LLM Providers

**Format**: `- [ ] TaskID [P?] [Story?] Description with file path`
- `[P]` — parallelisable (different files, no incomplete dependencies)
- `[US1/US2/US3]` — user story label (omitted in Setup, Foundational, Polish phases)

---

## Phase 1: Setup

**Purpose**: Add new runtime dependencies required by the document processing pipeline.

- [X] T001 Add `pymupdf==1.26.1`, `Pillow==11.2.1`, `PyYAML==6.0.2`, `python-dateutil==2.9.0.post0` to `backend/requirements.txt`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before any user story implementation begins.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Constitution Compliance Checks

- [X] T002 [P] Verify the 5 conditional edge predicates exist in `backend/src/state_machine.py` for all `Ingested → Parsed → PII_Redacted → Matched → Finalized` transitions — if a predicate is missing, add a no-op placeholder with a `# TODO` comment; do NOT modify node business logic
- [X] T003 [P] Verify PII redaction (`account_number → ****<last-4>`, SSN/address → `[REDACTED]`) fires before any downstream agent pass in `backend/src/agents/ingestion_agent.py`
- [X] T004 [P] Verify append-only audit log writer emits `input_hash`, `output_hash`, `rationale`, `confidence_scores`, no PII field values in `backend/src/audit/logger.py`
- [X] T005 [P] Verify no vendor LLM SDK imports (`langchain_openai`, `langchain_anthropic`, `langchain_google_genai`) exist outside `backend/src/adapters/llm_adapter.py`
- [X] T006 [P] Verify FastAPI OpenAPI auto-generation is active and document that `npm run generate:api` regenerates `frontend/src/generated/` DTOs after implementation

### New Infrastructure

- [X] T007 [P] Add `OUTPUT_DIRECTORY` env-var-backed setting to `backend/src/settings_store.py` — `SOURCE_DIRECTORY` and `WORK_DIRECTORY` already exist in production code (FR-001)
- [X] T008 Add `BatchRunModel`, `RunRecordModel`, `PaymentRecordModel` SQLAlchemy 2 ORM models to `backend/src/db/models.py` with all columns and indexes per `data-model.md §1`
- [X] T009 Create Alembic migration `backend/alembic/versions/XXXX_add_doc_processing_tables.py` — creates `batch_runs`, `run_records`, `payment_records` tables in FK dependency order (Decision 6)
- [X] T010 [P] Create `PaymentRecordCreate` and `PaymentRecordResponse` Pydantic v2 schemas in `backend/src/schemas/payment_record.py` per `data-model.md §2.1`
- [X] T011 [P] Create `RunStartedResponse`, `RunRecordSummary`, `BatchRunSummary`, `BatchRunDetail` Pydantic v2 schemas in `backend/src/schemas/run.py` per `data-model.md §2.2`
- [X] T012 [P] Add `output_directory: str` field to `LLMSettings` and `LLMSettingsResponse` in `backend/src/schemas/llm_settings.py` (Decision 7 / FR-001)
- [X] T013 Add `invoke_vision(prompt: str, images: list[str]) -> str` method to `LLMAdapter` in `backend/src/adapters/llm_adapter.py` using `HumanMessage` with structured content blocks (Decision 3)

**Checkpoint**: Foundation ready — all user story pipelines can now be implemented.

---

## Phase 3: User Story 1 — Trigger Pipeline from UI and Get Excel Output (Priority: P1) 🎯 MVP

**Goal**: Finance operator clicks Run Pipeline → backend scans source folder → pipeline extracts 14 payment fields per document via vision LLM → produces colour-coded `results.xlsx` and updates DB.

**Independent Test**: Configure `SOURCE_DIRECTORY`, `WORK_DIRECTORY`, `OUTPUT_DIRECTORY` in `.env`, place 3–5 sample documents in source folder, call `POST /api/v1/runs`, verify:
- Work folder contains GUID-named file copies
- `batch_runs` + `run_records` + `payment_records` rows exist in DB
- `results.xlsx` exists in output folder with correct columns and row colours
- `accuracy.jsonl` has one entry per processed document

### State and Config Scaffolding

- [X] T044 [P] [US1] Create `backend/src/graph/doc_pipeline/__init__.py` — new Python package; required before any node imports
- [X] T045 [P] [US1] Create `backend/src/services/__init__.py` — new Python package; required before `RunService` imports
- [X] T014 [P] [US1] Create `DocPipelineState` TypedDict and `PaymentRecordDict` TypedDict in `backend/src/graph/doc_pipeline/state.py` per `data-model.md §3.1`; also create `backend/tests/unit/test_doc_pipeline_state.py` with a structural type-shape test (assert all required keys present in `DocPipelineState.__annotations__`)
- [X] T015 [P] [US1] Create `backend/src/prompt_configs/` directory (if it doesn't exist) and YAML prompt config files `email.yaml`, `remittance.yaml`, `receipt.yaml`, `unknown.yaml` — each with `context_hint`, `field_hints`, `confidence_thresholds` (amount_paid ≥ 0.90), `required_fields` per `plan.md §Prompt Config Design`

### Pipeline Node Implementation (all in `backend/src/graph/doc_pipeline/nodes.py`)

- [X] T016 [US1] Implement `classifier_node`: render page 1 to base64 PNG via PyMuPDF, call `LLMAdapter.invoke_vision()`, parse `doc_type` ∈ {email, remittance, receipt, unknown}, load and cache YAML prompt config, write audit log entry, route to `error_node` on failure in `backend/src/graph/doc_pipeline/nodes.py`
- [X] T017 [US1] Implement `extractor_node`: render all pages to base64 PNG (PyMuPDF), Pillow-resize images where raw pixel buffer exceeds 20 MB to ≤ 4096px on longest side before encoding, call `LLMAdapter.invoke_vision()` per page with extraction prompt, parse JSON → `list[PaymentRecordDict]` (one per distinct amount, each tagged with `page_number` = 1-based page index), retry on parse failure up to 3 attempts, route to `error_node` on all-null or 3 parse failures, write audit log entry in `backend/src/graph/doc_pipeline/nodes.py`
- [X] T018 [US1] Implement `normaliser_node`: normalise `payment_date` → `YYYY-MM-DD`, `amount_paid`/`deductions` → `float`, `currency` → ISO 4217 code, `payment_method` → canonical form (EFT/CASH/CHEQUE/DIRECT_DEPOSIT/CARD), no LLM calls, write audit log entry in `backend/src/graph/doc_pipeline/nodes.py`
- [X] T019 [US1] Implement `validator_node`: load per-field thresholds from prompt config, apply three-rule priority logic (Extraction Failed → Review Required → Valid) per FR-009, write audit log entry using field names and confidence scores only (no PII values) in `backend/src/graph/doc_pipeline/nodes.py`
- [X] T020 [US1] Implement `excel_writer_node`: write audit log entry FIRST (constitution G7 — before any DB or file write), then batch-insert `validated_records` into `payment_records`, update `run_records` (status=Completed, record_count, completed_at), update `batch_runs` (total_records), append to `accuracy.jsonl` with all AccuracyLogEntry fields, rewrite `results.xlsx` with colour-coded rows and two sheets (Payment Records + Review Required) in `backend/src/graph/doc_pipeline/nodes.py`
- [X] T021 [US1] Implement `error_node`: write audit log entry, set `RunRecord.status = 'Failed'`, move source file to `{work_dir}/failed/`, return error state in `backend/src/graph/doc_pipeline/nodes.py`

### Graph and Service Assembly

- [X] T022 [US1] Assemble `DocPipeline` `StateGraph` in `backend/src/graph/doc_pipeline/pipeline.py`: add 5 nodes + `error_node`, wire conditional edges (`classifier_node → extractor_node or error_node`, etc.), compile graph, confirm `graph.get_graph().draw_mermaid()` runs without error
- [X] T023 [US1] Implement `RunService` in `backend/src/services/run_service.py`: `create_batch_run()` (DB insert + file scan + RunRecord creation), `process_batch()` async coroutine (sequential per-file graph invocation: set `RunRecord.status = 'Processing'` immediately before each `graph.invoke()` call, then AG-UI event emission), `asyncio.Queue` registry keyed by `batch_id` (Decision 5), dedup check per Decision 8
- [X] T024 [US1] Add `POST /api/v1/runs` endpoint to `backend/src/api/routes.py`: validate source directory exists, reject with 409 if a run is In Progress, create `BatchRun`, call `RunService.create_batch_run()`, fire `asyncio.create_task(process_batch(...))`, return `RunStartedResponse`

### Tests for User Story 1

- [X] T025 [P] [US1] Unit tests for `normaliser_node` — one test per normalisation rule (date formats → YYYY-MM-DD, amount string stripping → float, currency symbols/names → ISO 4217, payment_method variants → canonical form) per SC-006 in `backend/tests/unit/test_normaliser.py`
- [X] T026 [P] [US1] Unit tests for `validator_node` — all three `validation_status` branches with mock confidence scores above/below YAML thresholds in `backend/tests/unit/test_validator.py`
- [X] T047 [P] [US1] Unit tests for `classifier_node` — mock `LLMAdapter.invoke_vision()`, assert each `doc_type` value (`email`, `remittance`, `receipt`, `unknown`) is parsed correctly, assert `error_node` routing on parse failure and LLM exception in `backend/tests/unit/test_classifier.py`
- [X] T048 [P] [US1] Unit tests for `extractor_node` — mock `LLMAdapter.invoke_vision()` returning canned JSON; test retry logic (3 consecutive parse failures → `error_node`), all-null detection, and correct `page_number` tagging per extracted record in `backend/tests/unit/test_extractor.py`
- [X] T049 [US1] Implement HTTP 429 rate-limit handler in `extractor_node`: catch `langchain_core` `RateLimitError` (or equivalent), apply exponential backoff (5 s → 15 s → 45 s), then set `error_type='rate_limit'` and route to `error_node` after all retries exhausted; extend `backend/tests/unit/test_extractor.py` with a test asserting the backoff sequence and final `error_node` routing in `backend/src/graph/doc_pipeline/nodes.py`
- [X] T027 [US1] Integration test — full `DocPipeline` graph invocation with stub `LLMAdapter` returning canned JSON, assert `PaymentRecord` DB rows created, `RunRecord` status = Completed in `backend/tests/integration/test_doc_pipeline.py`

**Checkpoint**: User Story 1 fully functional — `POST /api/v1/runs` triggers pipeline and produces Excel output independently.

---

## Phase 4: User Story 2 — View Run History and Filter Results in the Browser (Priority: P2)

**Goal**: User opens Angular UI → sees run history list → clicks Run Pipeline (triggers via `RunsService`) → watches live per-file progress via AG-UI events → selects a completed run → browses filterable colour-coded results table.

**Independent Test**: Trigger a run via `POST /api/v1/runs`, open `/runs` in the Angular app, observe the run appear with status "In Progress" and progress counter updating live, then click the completed run row and verify the `/results` table shows all records with correct status chips and confidence scores.

### Backend Read Endpoints

- [X] T028 [US2] Add `GET /api/v1/runs` (list all, newest-first), `GET /api/v1/runs/{batch_id}` (BatchRunDetail with run_records), `GET /api/v1/results` (PaymentRecord list with filters: batch_id, doc_type, validation_status, `confidence_min`/`confidence_max` filtering against the `overall_confidence` DB column, skip, limit) endpoints to `backend/src/api/routes.py`
- [X] T029 [US2] Add `GET /api/v1/runs/{batch_id}/stream` SSE endpoint to `backend/src/api/routes.py`: drain `asyncio.Queue` for `batch_id`, yield `text/event-stream` frames, close stream on `BATCH_COMPLETED` (Decision 5)

### Frontend TypeScript Models

- [X] T030 [P] [US2] Add `BatchStartedEvent`, `FileStartedEvent`, `FileCompletedEvent`, `FileFailedEvent`, `BatchCompletedEvent` AG-UI event interfaces to `frontend/src/app/core/models/ag-ui.models.ts`
- [X] T031 [P] [US2] Create `RunStartedResponse`, `RunRecordSummary`, `BatchRunSummary`, `BatchRunDetail`, `PaymentRecordResponse`, `ResultsFilter` TypeScript interfaces in `frontend/src/app/core/models/run.models.ts`

### Frontend Services

- [X] T032 [P] [US2] Create `RunsService` with `startRun()`, `listRuns()`, `getRun(batchId)`, `getResults(filters: ResultsFilter)` methods in `frontend/src/app/core/services/runs.service.ts`
- [X] T033 [P] [US2] Extend `AgUiEventService` with `connectToBatch(batchId: string): void` method that opens `EventSource` to `/api/v1/runs/{batchId}/stream` and emits typed AG-UI batch events; also expose `isRunning: Signal<boolean>` — set to `true` on `BATCH_STARTED` event, `false` on `BATCH_COMPLETED` event — consumed by `RunsComponent` to disable the Run Pipeline button in `frontend/src/app/core/services/ag-ui-event.service.ts`

### Frontend Components

- [X] T034 [P] [US2] Create `RunsComponent` (standalone) in `frontend/src/app/features/runs/runs.component.ts`: run history list (batch_id, triggered_at, status chip, total_files, total_records), Run Pipeline button (disabled while `isRunning` signal is true), live progress indicator (`N of M files processed`) updated on `FILE_COMPLETED`/`FILE_FAILED` AG-UI events — navigate to `/results?batch_id=<id>` on row click
- [X] T035 [P] [US2] Create `ResultsComponent` (standalone) in `frontend/src/app/features/results/results.component.ts`: read `batch_id` from query params, load `PaymentRecord[]` via `RunsService.getResults()`, table with columns (Customer, Amount, Currency, Payment Date, Status, Confidence, Model, Source File), row colour (green/amber/red), filter panel by `validation_status`, `doc_type`, confidence range, expandable row showing per-field confidence scores

### Routing and Navigation

- [X] T036 [US2] Add `/runs` → `RunsComponent` and `/results` → `ResultsComponent` lazy routes to `frontend/src/app/app.routes.ts`
- [X] T037 [US2] Add "Run History" (→ `/runs`) and "Results" (→ `/results`) navigation links to `frontend/src/app/shared/shell/shell.component.ts`

### Tests for User Story 2

- [X] T038 [US2] Integration test for runs API: `POST /api/v1/runs` with mocked `RunService`, `GET /api/v1/runs`, `GET /api/v1/results` — assert correct HTTP status codes and response schema shapes; explicitly assert `POST /api/v1/runs` returns `409 Conflict` when a `BatchRun` with `status='In Progress'` already exists in DB in `backend/tests/integration/test_runs_api.py`
- [X] T046 [P] [US2] Angular unit tests for `RunsComponent` (Run Pipeline button disabled while `isRunning` signal is `true`) and `ResultsComponent` (filter by `validation_status` and `doc_type` narrows displayed rows) in `frontend/src/app/features/runs/runs.component.spec.ts` and `frontend/src/app/features/results/results.component.spec.ts` — required by SC-007

**Checkpoint**: User Stories 1 and 2 both independently testable — full pipeline trigger + live UI feedback + results browsing.

---

## Phase 5: User Story 3 — Monitor Accuracy and Compare LLM Providers (Priority: P3)

**Goal**: Developer runs pipeline with two different `LLM_PROVIDER` values and confirms each `accuracy.jsonl` entry contains distinct `llm_provider` and `llm_model` metadata for cross-provider quality analysis.

**Independent Test**: Set `LLM_PROVIDER=openai`, run pipeline, check `accuracy.jsonl` entry contains `llm_provider: "openai"`. Change to `LLM_PROVIDER=anthropic`, run again, confirm new entry has `llm_provider: "anthropic"` and all required AccuracyLogEntry fields per FR-010, FR-011.

### Accuracy Log Completeness

- [X] T039 [US3] Verify and complete `excel_writer_node` accuracy.jsonl output: confirm `llm_provider` and `llm_model` are read from settings and written to each `AccuracyLogEntry` alongside `timestamp`, `source_filename`, `doc_type`, `validation_status`, `overall_confidence` (mean of all field scores), `fields_extracted`, `null_fields`, `extraction_attempts` — patch `excel_writer_node` in `backend/src/graph/doc_pipeline/nodes.py` if any fields are missing
- [X] T040 [P] [US3] Unit test for `accuracy.jsonl` AccuracyLogEntry format: mock `excel_writer_node`, assert all 10 required fields are present and correctly typed, including `llm_provider` and `llm_model` in `backend/tests/unit/test_accuracy_log.py`

**Checkpoint**: All three user stories independently functional and testable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, DTO regeneration, and end-to-end smoke test.

- [X] T041 Validate `DocPipeline` graph Mermaid output: call `get_doc_pipeline().get_graph().draw_mermaid()` in a test or Python shell and confirm it renders without error per SC-008 in `backend/src/graph/doc_pipeline/pipeline.py`
- [X] T042 Regenerate Angular DTOs: with the backend running, execute `npm run generate:api` from `frontend/` to update `frontend/src/generated/` — confirm `RunsService` and `ResultsComponent` compile cleanly against the generated types (constitution G9 compliance)
- [X] T043 Run full end-to-end validation per `specs/001-multi-agent-doc-processing/quickstart.md`: configure env vars, place sample documents in source folder, click Run Pipeline in the Angular UI, verify `results.xlsx` produced, DB records correct, `accuracy.jsonl` written, SC-001 through SC-008 all pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** → No dependencies. Start immediately.
- **Foundational (Phase 2)** → Requires Phase 1. **BLOCKS all user stories.**
- **US1 (Phase 3)** → Requires Phase 2. MVP — deliver first.
- **US2 (Phase 4)** → Requires Phase 2 (T008, T009, T010, T011) + Phase 3 (T022–T024 backend routes). Frontend work (T030–T037) can begin in parallel with Phase 3 once T030/T031 models are done.
- **US3 (Phase 5)** → Requires Phase 3 (T020 `excel_writer_node`). Verification-only — thin phase.
- **Polish (Phase 6)** → Requires all desired user stories complete.

### User Story Dependencies

| Story | Can Start After | Depends on Other Stories? |
|---|---|---|
| US1 | Phase 2 complete | Independent |
| US2 Frontend | T030/T031 done (models) | Independent of US1 frontend; needs US1 API (T028/T029) for full integration |
| US2 Backend | T022/T023/T024 (US1) | US1 backend must be complete |
| US3 | T020 (US1 excel_writer_node) | US1 `excel_writer_node` must be implemented |

### Critical Sequence Within US1

```
T014/T015 (state + configs) ──→ T016 (classifier_node)
                              ──→ T017 (extractor_node)    ← all nodes depend on T014
                              ──→ T018 (normaliser_node)      (same file: nodes.py —
                              ──→ T019 (validator_node)        implement sequentially)
                              ──→ T020 (excel_writer_node)
                              ──→ T021 (error_node)
                                       │
                                       ▼
                                   T022 (pipeline.py)
                                       │
                                       ▼
                                   T023 (run_service.py)
                                       │
                                       ▼
                                   T024 (routes.py POST /runs)
```

### Parallel Opportunities Per Story

#### Phase 2 Parallel Batch
```
T002 (state_machine.py)
T003 (ingestion_agent.py)
T004 (audit/logger.py)        ← all run in parallel
T005 (no-file check)
T006 (settings_store.py)
T010 (schemas/payment_record.py)
T011 (schemas/run.py)
T012 (schemas/llm_settings.py)
```

#### US1 Parallel Batch (once T014 done)
```
T025 (test_normaliser.py)     ← parallel with T018 implementation
T026 (test_validator.py)      ← parallel with T019 implementation
```

#### US2 Parallel Batch (once T031 done)
```
T032 (runs.service.ts)
T033 (ag-ui-event.service.ts) ← parallel with each other
```
Then once T032/T033 done:
```
T034 (runs.component.ts)
T035 (results.component.ts)   ← parallel with each other
```

---

## Implementation Strategy

**MVP scope**: Phase 1 + Phase 2 + Phase 3 (US1) = the complete backend pipeline producing Excel output. This alone satisfies the primary value proposition (SC-001 through SC-006).

**Increment 2**: Phase 4 (US2) adds the full Angular UI experience — run history, live progress, results table.

**Increment 3**: Phase 5 (US3) + Phase 6 (Polish) — accuracy monitoring and final validation.

**Suggested delivery order**:
1. T001 → T002–T013 (foundation, ~1–2 hours)
2. T014–T024 (US1 pipeline, ~4–6 hours)
3. T025–T027 (US1 tests, ~1–2 hours)
4. T028–T038 (US2 full stack, ~3–4 hours)
5. T039–T043 (US3 + polish, ~1 hour)

# Research: Multi-Agent Document Processing System

**Branch**: `001-multi-agent-doc-processing`  
**Date**: 2026-03-25  
**Status**: Complete — all NEEDS CLARIFICATION items resolved

---

## Decision 1: PDF-to-Image Rendering Library

**Decision**: `PyMuPDF` (`pymupdf`) for all PDF-to-image rendering.

**Rationale**: Pure-Python binding to MuPDF — no external system dependencies such as poppler or Ghostscript required. Works inside Docker without extra `apt-get` steps. Handles PDF, TIFF, BMP, WebP, JPEG, PNG, and XPS natively. Fast per-page `Pixmap` rendering with configurable DPI. Already supports the 20 MB resize edge case via `Pixmap.shrink()`.

**Alternatives Considered**:
- `pdf2image` — requires `poppler-utils` installed at system level in the container. Additional Dockerfile complexity and brittle version coupling.
- `wand` (ImageMagick binding) — requires ImageMagick binary. Heavier image footprint.

**New Dependency**: `pymupdf==1.26.1` (add to `requirements.txt`)

---

## Decision 2: Image Resize for Oversized Documents

**Decision**: `Pillow` (`PIL`) for the edge-case image resize (>20 MB → longest side ≤ 4096 px).

**Rationale**: Already the de-facto standard for Python image manipulation. Lightweight, no system deps. Provides `Image.thumbnail()` for proportional resize respecting aspect ratio. Works in-memory on the base64-decoded bytes without writing to disk.

**Alternatives Considered**:
- OpenCV — too heavy for a single resize operation.
- PyMuPDF's own `Pixmap.shrink()` — works but limited to power-of-2 shrink factors. Pillow gives finer-grained control.

**New Dependency**: `Pillow==11.2.1` (add to `requirements.txt`)

---

## Decision 3: Multimodal LangChain Image Format

**Decision**: LangChain `HumanMessage` with structured `content` list using `{"type": "image_url", "image_url": {"url": "data:image/png;base64,<b64>"}}` content blocks.

**Rationale**: LangChain's unified message format is provider-agnostic. `langchain-openai`, `langchain-anthropic`, and `langchain-google-genai` (all already in `requirements.txt`) each translate this format natively to their provider's API. The `LLMAdapter` wraps the model as a `BaseChatModel` — no conditional branches in node code per the LLM adapter boundary rule (constitution §Tech Stack).

**Implementation**: A new `invoke_vision(prompt: str, images: list[str]) -> str` method on `LLMAdapter` that constructs the structured `HumanMessage` and calls `self.model.invoke(...)`.

**Alternatives Considered**:
- Provider-specific SDK calls — PROHIBITED by constitution LLM adapter boundary.
- Passing image paths and letting each provider load them — not supported across all providers; forces provider detection logic in node code.

---

## Decision 4: YAML Prompt Configuration

**Decision**: `PyYAML` for loading per-doc-type prompt configs from `backend/src/prompt_configs/`.

**Rationale**: Standard Python YAML library. Config files are static per doc type and loaded at pipeline startup (cached). Four config files: `email.yaml`, `remittance.yaml`, `receipt.yaml`, `unknown.yaml`. Each defines `context_hint`, `field_hints`, `confidence_thresholds`, and `required_fields`.

**New Dependency**: `PyYAML==6.0.2` (add to `requirements.txt`)

---

## Decision 5: AG-UI Batch Progress Streaming Pattern

**Decision**: Separate per-run SSE endpoint (`GET /api/runs/{batch_id}/stream`) plus an in-memory `asyncio.Queue` per active batch.

**Rationale**:
- `POST /api/runs` → creates `BatchRun` immediately, starts async processing in the background, returns `{batch_id, total_files, status}` JSON. Allows Angular to redirect to run detail within <100 ms.
- Angular then opens `EventSource` to `GET /api/runs/{batch_id}/stream` to receive per-file progress events.
- The asyncio Queue decouples the processing loop (producer) from the SSE stream (consumer). Queues are keyed by `batch_id` in a module-level dict; cleaned up on `BATCH_COMPLETED`.
- Existing `/api/v1/agents/stream` for the reconciliation pipeline is untouched.

**New Event Types**:

| Event | Fields |
|---|---|
| `BATCH_STARTED` | `batch_id`, `total_files` |
| `FILE_STARTED` | `batch_id`, `run_record_id`, `source_filename`, `file_index`, `total_files` |
| `FILE_COMPLETED` | `batch_id`, `run_record_id`, `source_filename`, `record_count`, `validation_summary` |
| `FILE_FAILED` | `batch_id`, `run_record_id`, `source_filename`, `error` |
| `BATCH_COMPLETED` | `batch_id`, `total_files`, `total_records`, `status_summary` |

**Alternatives Considered**:
- WebSocket — heavier, bidirectional not needed.
- Polling `GET /api/runs/{batch_id}` — creates N-second latency on status updates and chatty DB queries.
- Reusing `/agents/stream` — would conflate two independent pipelines and break the existing reconciliation UI.

---

## Decision 6: New Tables vs. Existing Schema

**Decision**: Add three new ORM models to `backend/src/db/models.py`: `BatchRunModel`, `RunRecordModel`, `PaymentRecordModel`. Generate a new Alembic migration file.

**Rationale**: Existing tables (`documents`, `bank_transactions`, `match_results`, `audit_log`) are for the reconciliation pipeline. The new document processing pipeline needs separate tables to avoid coupling. The Alembic migration file ensures Docker auto-migration on container start.

**`BatchRunModel`** (`batch_runs` table): one row per UI-triggered run.  
**`RunRecordModel`** (`run_records` table): one row per file within a run.  
**`PaymentRecordModel`** (`payment_records` table): one row per extracted payment amount.

---

## Decision 7: `output_directory` Setting Addition

**Decision**: Add `output_directory: str` to `LLMSettings` with `OUTPUT_DIRECTORY` env var fallback. Also add `output_directory` to `LLMSettingsResponse`. Expose via existing `/api/v1/settings/llm` GET/PUT endpoints.

**Rationale**: Spec FR-001 requires all folder paths configurable. Currently `source_directory`, `work_directory`, `review_directory` are present but `output_directory` (for `results.xlsx` and `accuracy.jsonl`) is missing. The settings endpoint is already PUT-capable so no new API surface needed.

---

## Decision 8: Deduplication of Already-Processed Files

**Decision**: Before processing each file in the batch, check whether its `source_filename` already appears in an existing `RunRecord` with status `Completed` for that batch. Skip and emit `FILE_SKIPPED` event if found.

**Rationale**: Edge case from spec — "if accuracy.jsonl already contains an entry for that source_filename, skip it." Using the database (which is the authoritative record) is more robust than parsing the JSONL file. The JSONL is a secondary accuracy log, not the dedup index.

---

## Decision 9: DocPipelineState — New TypedDict

**Decision**: `DocPipelineState` is a new, separate `TypedDict` in `backend/src/graph/doc_pipeline/state.py`. The existing `ContraState` in `backend/src/graph/state.py` is not modified.

**Rationale**: The two pipelines are independent. The reconciliation pipeline (ContraState) and the document processing pipeline (DocPipelineState) have incompatible field sets. Sharing state would create tight coupling and risk regressions in the existing pipeline.

---

## Decision 10: LangGraph Graph Isolation

**Decision**: New `StateGraph` defined in `backend/src/graph/doc_pipeline/pipeline.py`. The existing `backend/src/graph/pipeline.py` graph is unchanged.

**Rationale**: Keeps the reconciliation pipeline stable. The doc processing pipeline uses its own nodes, state, and compilation. Both graphs can co-exist in the same FastAPI process.

---

## Decision 11: Confidence Threshold — Per-field YAML vs. Constitution 0.85

**Decision**: For the document processing pipeline, use YAML per-field thresholds (default 0.70) as defined in spec FR-007/FR-007a. The constitution's 0.85 blanket threshold applies to the existing reconciliation pipeline's OCR agent.

**Rationale**: The constitution was written for the reconciliation pipeline where a missed OCR confidence gate = potential financial fraud. The new pipeline is a data extraction catalogue where validation status is visible and transparent in the output. The per-field YAML approach is MORE configurable — YAML files may set individual thresholds at or above 0.85 for critical fields (e.g., `amount_paid`). This is documented as a context-specific justified override, not a constitution violation.

**Constitution Compliance Note**: The YAML threshold for `amount_paid` MUST be set to 0.85 or above in all shipped prompt configs to align with the spirit of the Vision Agent protocol. A `required_fields` check in the Validator node enforces `amount_paid` as critical.

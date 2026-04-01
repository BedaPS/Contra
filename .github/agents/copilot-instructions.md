# Contra Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-31

## Active Technologies

### Backend
- **Python 3.12+** with FastAPI 0.135.2
- **LangGraph 1.1.3** — StateGraph-based orchestration (two independent graphs: reconciliation pipeline + doc processing pipeline)
- **LangChain-core 1.2.20** — BaseChatModel for all LLM calls (provider-agnostic)
- **SQLAlchemy 2.0.48** + pymssql 2.3.13 — MSSQL 2022, code-first ORM, Alembic migrations
- **openpyxl 3.1.5** — Excel output generation
- **PyMuPDF 1.26.1** — PDF-to-image rendering (all pages as base64 PNG)
- **Pillow 11.2.1** — Image resize for oversized documents (>20 MB → ≤ 4096px longest side)
- **PyYAML 6.0.2** — Per-doc-type prompt configurations (`prompt_configs/`)
- **pytest 8.4.1** + httpx AsyncClient + pytest-asyncio

### Frontend
- **Angular 21.2.5** — standalone components only (`standalone: true`), strict TypeScript
- **RxJS 7.8.2** — BehaviorSubject at service boundaries; Signals for internal state
- **@ag-ui/core 0.0.47** — AG-UI protocol for SSE real-time event streaming
- **Angular Jasmine/Karma** — frontend testing

## Project Structure

```text
backend/
├── src/
│   ├── graph/
│   │   ├── state.py              # ContraState — reconciliation pipeline state
│   │   ├── nodes.py              # Reconciliation pipeline nodes
│   │   ├── pipeline.py           # Reconciliation StateGraph
│   │   └── doc_pipeline/         # NEW (feature 001)
│   │       ├── state.py          # DocPipelineState TypedDict + PaymentRecordDict
│   │       ├── nodes.py          # classifier, extractor, normaliser, validator, excel_writer
│   │       └── pipeline.py       # Doc processing StateGraph
│   ├── db/
│   │   ├── models.py             # ORM models (existing + BatchRunModel, RunRecordModel, PaymentRecordModel)
│   │   ├── engine.py             # SessionLocal, get_db()
│   │   └── base.py               # DeclarativeBase
│   ├── adapters/
│   │   └── llm_adapter.py        # ONLY place for LLM calls; invoke_vision() added for multimodal
│   ├── services/
│   │   └── run_service.py        # NEW: BatchRun/RunRecord CRUD + async batch orchestration
│   ├── schemas/
│   │   ├── payment_record.py     # NEW: PaymentRecordCreate, PaymentRecordResponse
│   │   ├── run.py                # NEW: RunStartedResponse, BatchRunSummary, BatchRunDetail
│   │   └── llm_settings.py       # LLM settings + output_directory
│   ├── prompt_configs/           # NEW: YAML per doc-type (email, remittance, receipt, unknown)
│   ├── api/
│   │   └── routes.py             # FastAPI routers (existing + /runs, /results, SSE stream)
│   ├── audit/
│   │   └── logger.py             # Append-only audit log
│   └── settings_store.py         # Env-driven config (SOURCE/WORK/OUTPUT_DIRECTORY)
├── alembic/versions/             # Migrations — one new: add_doc_processing_tables
└── requirements.txt              # Exact pinned versions — no ranges

frontend/
├── src/app/
│   ├── core/
│   │   ├── models/
│   │   │   ├── ag-ui.models.ts   # AG-UI event interfaces (batch events added)
│   │   │   └── run.models.ts     # NEW: BatchRun, RunRecord, PaymentRecord TS types
│   │   └── services/
│   │       ├── ag-ui-event.service.ts  # SSE subscription (connectToBatch() added)
│   │       └── runs.service.ts         # NEW: HTTP /runs, /results calls
│   ├── features/
│   │   ├── runs/                 # NEW: Run history + Run Pipeline button + live progress
│   │   └── results/              # NEW: Filterable PaymentRecord results table
│   └── generated/                # OpenAPI-generated DTOs — DO NOT EDIT MANUALLY
```

## Commands

```bash
# Docker (recommended) — starts backend + MSSQL
docker compose up --build

# Backend local dev
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.api.main:app --reload

# Run backend tests
pytest tests/ -v

# Frontend
cd frontend
npm ci
npx ng serve

# Regenerate Angular DTOs from OpenAPI (backend must be running)
npm run generate:api
```

## Code Style

### Python
- Pydantic v2 models for all schemas — no raw `dict` in business logic
- Type hints on every function signature; `Any` requires inline justification comment
- FastAPI dependency injection for DB sessions and adapters
- All LLM calls through `LLMAdapter` in `backend/src/adapters/llm_adapter.py` — no vendor imports elsewhere
- No raw SQL — SQLAlchemy ORM only

### TypeScript / Angular
- Standalone components with `standalone: true` — no NgModules
- Strict null checks; `!` non-null assertions require a comment
- Signals over RxJS Subjects for internal component state
- HTTP calls via generated `frontend/src/generated/` services — no raw `HttpClient` in components
- No `any` types in production code

## Recent Changes

### Feature 001 — Multi-Agent Document Processing System (branch: `001-multi-agent-doc-processing`, 2026-03-25)
Added a new LangGraph vision extraction pipeline:
- **New graph**: `backend/src/graph/doc_pipeline/` — 5-node pipeline: `classifier_node → extractor_node → normaliser_node → validator_node → excel_writer_node`
- **New DB tables**: `batch_runs`, `run_records`, `payment_records` via Alembic migration
- **New routes**: `POST /api/v1/runs`, `GET /api/v1/runs`, `GET /api/v1/runs/{batch_id}`, `GET /api/v1/results`, SSE stream endpoint
- **New frontend components**: `RunsComponent` (`/runs`) with live progress, `ResultsComponent` (`/results`) with filterable table
- **New dependencies**: PyMuPDF, Pillow, PyYAML (backend)
- **LLM adapter extended**: `invoke_vision(prompt, images)` multimodal method added

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->

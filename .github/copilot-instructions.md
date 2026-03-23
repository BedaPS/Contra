# Contra — GitHub Copilot Instructions

> **Status**: Active implementation. Backend and frontend scaffolded. LangGraph pipeline operational.  
> **Constitution**: `.specify/memory/constitution.md` v2.0.0 — read it before touching agent logic, schemas, or state transitions. It is the authority in any conflict.

---

## Project in one sentence

Contra is an LLM-powered financial reconciliation pipeline: it ingests payment proof from emails (OCR), matches documents against bank statements (fuzzy matching), and generates verified receipts — with a complete audit trail.

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Backend | Python 3.12+, FastAPI | `venv` only; all deps pinned to exact versions in `requirements.txt` |
| Frontend | Angular (latest stable LTS), TypeScript strict mode | Standalone components default; `any` types FORBIDDEN in production code |
| Agent Orchestration | LangGraph (StateGraph) | Agents are graph nodes; shared `ContraState` TypedDict; conditional edges enforce gates |
| Agent LLM | LangChain BaseChatModel | All LLM calls through `backend/src/adapters/llm_adapter.py` only |
| HITL | LangGraph `interrupt()` | Pause/resume at `Needs_Review`, `Human_Review`, `Exception_Review` |
| Database | MSSQL + SQLAlchemy 2.x + pymssql | Code-first ORM; `DATABASE_URL` env var; no raw SQL in business logic |
| Deployment | Docker Compose | Backend + MSSQL; entrypoint auto-creates DB and runs Alembic migrations |
| API contract | OpenAPI (FastAPI auto-gen) | Angular consumes only generated DTOs — never hand-written duplicate interfaces |

---

## Repository Layout

```
backend/
├── src/
│   ├── graph/            # LangGraph pipeline — THE orchestration layer
│   │   ├── state.py      # ContraState TypedDict — shared state for all nodes
│   │   ├── nodes.py      # Node functions (ingest, ocr, pii, match, finalize, HITL)
│   │   └── pipeline.py   # StateGraph definition, conditional edges, compilation
│   ├── db/               # SQLAlchemy ORM — persistence layer
│   │   ├── engine.py     # Engine, SessionLocal, get_db() dependency
│   │   ├── base.py       # DeclarativeBase
│   │   └── models.py     # ORM models (DocumentModel, BankTransactionModel, etc.)
│   ├── agents/           # Legacy agent modules (business logic preserved in nodes.py)
│   ├── adapters/         # llm_adapter.py — LangChain BaseChatModel wrapper (ONLY LLM calls)
│   ├── schemas/          # parsed_document.py, match_result.py (Pydantic)
│   ├── state_machine.py  # Legacy linear state machine (superseded by graph/pipeline.py)
│   ├── audit/            # logger.py — append-only reasoning log
│   └── api/              # FastAPI routers + SSE streaming from LangGraph
├── tests/
│   ├── unit/
│   ├── integration/
│   └── contract/
├── requirements.txt      # exact pinned versions — no ranges
└── .env.example

frontend/
├── src/
│   ├── app/
│   │   ├── core/         # auth, HTTP interceptors, guards
│   │   ├── features/     # one folder per UI feature (standalone components)
│   │   └── shared/       # reusable standalone components
│   └── generated/        # OpenAPI-generated DTOs — DO NOT EDIT MANUALLY
├── package.json          # exact pinned versions — no ranges
└── angular.json
```

---

## Build & Run Commands

```bash
# Docker (recommended) — starts backend + MSSQL
docker compose up --build

# Docker (detached)
docker compose up --build -d

# Stop
docker compose down

# Backend (local development without Docker)
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

# Build frontend
npx ng build

# Generate Angular DTOs from OpenAPI (backend must be running)
npm run generate:api
```

---

## Speckit Workflow (spec-driven development)

This project uses [speckit](https://github.com/speckit). Use the VS Code slash commands in order:

| Step | Command | Output |
|---|---|---|
| 1 | `/speckit.specify` | `specs/<feature>/spec.md` |
| 2 | `/speckit.plan` | `specs/<feature>/plan.md` + design artifacts |
| 3 | `/speckit.tasks` | `specs/<feature>/tasks.md` |
| 4 | `/speckit.implement` | Source code in `backend/` and `frontend/` |

Optional quality gates: `/speckit.clarify` (before plan), `/speckit.analyze` and `/speckit.checklist` (after tasks).

---

## Critical Rules for AI Agents

These rules are derived from the constitution. Violating any of them is a constitution breach — not a suggestion to reconsider.

### 1. Zero Variance (amounts)
`bank_amount − email_amount` MUST equal exactly `$0.00`. Any non-zero delta routes to `Exception_Review`. No rounding, no silent tolerance.

### 2. Bank Statement is Truth
An email claim with no matching bank entry is `Pending`, NEVER `Paid`. If a Bank Reference ID is present in either source, it takes 100% precedence over name similarity — skip all other matching criteria.

### 3. PII Redaction is non-bypassable
The Ingestion Agent MUST redact all PII before passing data downstream. Full account numbers, SSNs, and addresses MUST NOT appear in agent payloads, API responses, or logs. Use `****<last-4>` for account numbers and `[REDACTED]` for everything else.

### 4. Vision Agent confidence gate
Every OCR field must carry a `confidence_score`. Any field below `0.85` → status `NEEDS_REVIEW` → document is BLOCKED from advancing to matching. No exceptions.

### 5. Auditor Agent matching rules
- Levenshtein name similarity threshold: **≥ 0.90**. Below threshold = not a match.
- Temporal window: **7 calendar days** inclusive.
- Duplicate candidates (two identical bank transactions for one email): set both to `LOCKED`, escalate to `Human_Review`. Never auto-select.

### 6. State machine is a LangGraph StateGraph
States: `Ingested → Parsed → PII_Redacted → Matched → Finalized` (happy path)  
Gate checks are enforced as conditional edge predicates. Error states and HITL interrupts branch off the happy path. Cyclic sub-graphs allowed with max-iteration guards (default: 3). Skipping a gate is PROHIBITED.

### 7. Audit log: append-only, every transition
Before completing any state transition, every agent MUST write a reasoning log entry to the audit DB. The entry MUST include `input_hash`, `output_hash`, `rationale`, and `confidence_scores`. No PII in logs.

### 8. LLM adapter boundary
ALL LLM provider calls go through a LangChain `BaseChatModel` configured in `backend/src/adapters/llm_adapter.py`. Vendor SDK imports anywhere else are FORBIDDEN. Switching LLM providers must require only configuration changes.

### 9. Human-in-the-Loop (HITL)
LangGraph `interrupt()` pauses execution at `Needs_Review`, `Human_Review`, and `Exception_Review`. Resume with `Command(resume={...})` containing reviewer identity and rationale. Anonymous resumes are PROHIBITED. HITL actions are logged to the audit trail.

---

## Code Style Quick-Reference

**Python (backend)**
- Pydantic v2 models for all schemas; no raw `dict` in business logic
- FastAPI dependency injection for DB sessions and adapter instances
- Type hints on every function signature; `Any` type requires a comment justifying it
- `pytest` + `httpx AsyncClient` for API tests; `pytest-asyncio` for async tests

**TypeScript (frontend)**
- Angular standalone components (`standalone: true`) — no NgModules unless forced by a library
- Strict null checks; no `!` non-null assertions without a comment
- Signals over RxJS Subjects for internal state; BehaviorSubject only at service boundaries
- HTTP calls via generated service from `frontend/src/generated/` — no raw `HttpClient` in components

---

## Pitfalls to Avoid

| Pitfall | Why it's wrong |
|---|---|
| Matching by name alone when Bank Ref ID exists | Violates Source of Truth Hierarchy (constitution §II) |
| Emitting `MATCHED` with delta ≠ $0.00 | Violates Zero Variance (constitution §I) |
| Passing raw PII to auditor agent | Violates Privacy Mandate (constitution §III) |
| Writing LLM calls outside `llm_adapter.py` | Breaks provider-agnostic contract |
| Importing vendor SDKs in graph nodes | All LLM calls go through BaseChatModel from the adapter |
| Skipping `interrupt()` at NEEDS_REVIEW/HUMAN_REVIEW | Constitution HITL protocol requires pause for human input |
| Cycles without max-iteration guard | Can cause infinite loops in the graph |
| Using `any` type in Angular components | Forbidden by Tech Stack Constraints |
| Hand-editing `frontend/src/generated/` | DTOs are generated — edits are overwritten on next `generate:api` run |
| Floating version ranges in `requirements.txt` / `package.json` | Breaks reproducible builds; constitution prohibits it |
| Using raw SQL in business logic | All DB access must go through SQLAlchemy ORM |
| Hardcoding database credentials | Use `DATABASE_URL` env var; never commit secrets |

---

## Linked References

| Document | Purpose |
|---|---|
| [.specify/memory/constitution.md](../.specify/memory/constitution.md) | Full constitutional rules — authoritative |
| [.specify/templates/plan-template.md](../.specify/templates/plan-template.md) | Constitution Check gate table for implementation plans |
| [README.md](../README.md) | Project overview |

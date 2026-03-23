<!--
SYNC IMPACT REPORT
==================
Version Change   : 2.1.0 → 2.2.0 (MINOR — Deployment section added;
                   Docker Compose for backend + MSSQL; entrypoint with
                   auto-migration; CORS_ORIGINS env var)
Modified Principles : N/A — existing principles unchanged.
Added Sections   :
  - Deployment — Docker Compose orchestration for backend + MSSQL.
    Backend image built from `backend/Dockerfile`. Entrypoint creates
    database and runs Alembic migrations before starting uvicorn.
Modified Sections:
  - Tech Stack Constraints — added CORS_ORIGINS env var, Docker deployment note.
Removed Sections : N/A
Templates Updated:
  ✅ .specify/templates/plan-template.md — No changes required
  ✅ .specify/templates/tasks-template.md — No changes required
  ✅ .specify/templates/spec-template.md — No changes required
Follow-up TODOs  : None — all fields resolved.
-->

# Contra Constitution

## Core Principles

### I. Rule of Zero Variance

The delta between a bank transaction amount and its matched email claim MUST equal
exactly $0.00. Rounding up or down is FORBIDDEN.

A non-zero delta is only permissible when a named **Fee Logic** override is explicitly
configured in system settings, applied programmatically, and written to the audit log
before the match is accepted. Undocumented tolerance of any non-zero delta is a
constitution violation.

Any match attempt that produces a non-zero unadjusted delta MUST be routed to
`Exception_Review` immediately. Silent pass-through is PROHIBITED.

**Rationale**: Cent-level errors compound across high-volume transaction sets and
destroy financial audit integrity. Accuracy over speed — always.

### II. Source of Truth Hierarchy

The Bank Statement is the single authoritative source of truth. No other source
overrides it.

Match precedence order (highest → lowest):

1. **Bank Reference ID** — if present in either source, it takes 100% precedence.
   All other criteria are bypassed. This is unconditional.
2. **Amount + Date match** — exact cent match within the 7-day temporal window.
3. **Name Similarity** — Levenshtein score ≥ 0.90, used only when (1) and (2) are
   inconclusive.

An email payment claim with no corresponding bank entry MUST be classified as
`Pending`. It MUST NOT be classified as `Paid` under any circumstance.

**Rationale**: False positives (wrong person matched) constitute financial fraud
exposure. False negatives (missed match) are recoverable manual tasks. Accuracy
over speed — always.

### III. Privacy Mandate

The Ingestion Agent MUST redact all PII fields before any data is passed to any
downstream agent, service, or LLM. This gate is non-negotiable and non-bypassable.

PII categories subject to mandatory redaction:

- Full bank account numbers and routing numbers → masked as `****<last-4-digits>`
- National identification numbers (SSN, tax ID) → masked as `[REDACTED]`
- Home and billing addresses → masked as `[REDACTED]`
- Any field not required for matching logic MUST be dropped, not masked

Full PII values MUST NOT appear in: agent inputs, agent outputs, API responses,
database records (outside the encrypted vault), or audit logs.

**Rationale**: Downstream agents — including third-party LLMs — must never receive
raw PII. Exposure is a liability regardless of model provider or hosting arrangement.

## Agent Protocols

### Vision Agent (OCR) Protocol

**Confidence Score**: Every extracted field MUST include a `confidence_score`
(float, range 0.0–1.0). This field is mandatory in the output schema — omitting it
is a schema violation.

**Red Flag Rule**: Any field with `confidence_score < 0.85` MUST be flagged with
status `NEEDS_REVIEW`. The document MUST NOT advance to the Matching stage until a
human reviewer clears the flag. Proceeding past an uncleared flag is PROHIBITED.

**No Inference Rule**: The agent MUST NOT guess, infer, or extrapolate illegible
characters or digits. Ambiguous values MUST be returned as `null` with a
correspondingly low confidence score. Fabricating a value is a constitution violation.

**Output Contract**: All output MUST be valid JSON conforming to the
`ParsedDocument` schema (defined in `backend/src/schemas/parsed_document.py`).
Conversational prose, markdown, or any non-JSON output is PROHIBITED.

### Auditor Agent (Matching) Protocol

**Bank Reference ID Supremacy**: If a Bank Reference ID is present in the bank
record or the parsed document, it takes 100% precedence. The agent MUST use it as
the sole match key. Name similarity scoring MUST be skipped. This rule is
unconditional.

**Name Similarity Threshold**: When Bank Reference ID is absent, name matching MUST
use Levenshtein distance. The required minimum similarity score is **0.90**. A score
below 0.90 is NOT a match — the agent MUST NOT promote it to a match by any means.

**Temporal Window**: A parsed email date and a bank transaction date MUST be within
7 calendar days of each other (inclusive). Matches outside this window are INVALID
regardless of amount, name score, or reference ID.

**Duplicate Lock Rule**: If one email maps to two or more bank transactions with
identical amounts and dates, the agent MUST set all candidate transactions to
`LOCKED` status and escalate to `Human_Review`. Auto-selecting any candidate is
FORBIDDEN.

**No Assumption Rule**: The agent MUST NOT emit a `MATCHED` status unless ALL of
the following are simultaneously satisfied: amount delta = $0.00, temporal window
satisfied, and either Bank Reference ID matches or name similarity ≥ 0.90. Any
unsatisfied criterion routes to `Exception_Review`.

**Output Contract**: The agent MUST output only the final Match JSON object. No
explanatory text, no markdown — only the JSON defined in
`backend/src/schemas/match_result.py`.

**System Prompt Injection**: At initialization, the Auditor Agent's system prompt
MUST include: *"You are the Auditor Agent of Contra. You operate under the Contra
Constitution. Your primary directive is precision. You are forbidden from assuming a
match. If a Bank Reference ID is present, it takes 100% precedence over Name
Similarity. Do not output anything except the final Match JSON."*

## State Machine Enforcement

The reconciliation pipeline is implemented as a **LangGraph `StateGraph`**
(`backend/src/graph/pipeline.py`). All documents flow through the graph, and
shared state is maintained in a typed `ContraState` dictionary
(`backend/src/graph/state.py`).

### Core States (preserved)

Every document MUST traverse the following states. Gate checks are enforced as
**conditional edge predicates** or **node-level assertions** — a failing gate
routes the document to the designated error state. There is no silent pass-through.

| State | Entry Constraint | Failure Route |
|---|---|---|
| `Ingested` | Attachment MIME type MUST be `application/pdf` or `image/*` | → `Error_Queue` |
| `Parsed` | `amount` and `account_name` MUST be non-null and non-empty | → `Incomplete_Data` |
| `PII_Redacted` | All PII fields MUST be masked; unmasked PII fields MUST NOT exist in the payload | → `Error_Queue` |
| `Matched` | `bank_amount − email_amount = $0.00` AND `confidence_score ≥ 0.85` AND name similarity ≥ 0.90 (or Bank Ref ID match) AND date within 7-day window | → `Exception_Review` |
| `Finalized` | Receipt MUST be dispatched to the original sender email address | → `Audit_Trail_Failure` |

### Graph Architecture Rules

**Shared State**: All nodes operate on a single `ContraState` TypedDict. Nodes
receive the full state, perform their work, and return a partial state update that
LangGraph merges back. Direct mutation of state outside the returned dict is
PROHIBITED.

**Conditional Edges**: After each processing node, a routing function (conditional
edge) evaluates gate checks and directs the document to the next node or an error
node. These routing functions are the canonical gate enforcement mechanism.

**Cyclic Sub-Graphs**: Enterprise extensions (e.g., multi-round OCR correction,
iterative matching refinement) MAY introduce cycles. Each cycle MUST include a
**max-iteration guard** to prevent infinite loops. The guard default is 3 iterations
unless explicitly overridden in configuration.

**Error Nodes**: Error states (`Error_Queue`, `Incomplete_Data`, `Exception_Review`,
`Needs_Review`, `Human_Review`, `Audit_Trail_Failure`) are terminal or interrupt
nodes in the graph. A document routed to an error node MUST NOT re-enter the happy
path without human intervention (via HITL interrupt).

**Atomicity**: State transitions within the graph MUST be logged to the audit trail
before the next node executes. LangGraph checkpointing provides the persistence
layer for rollback-on-failure.

**Checkpointing**: LangGraph's built-in checkpoint system MUST be enabled. This
enables replay, rollback, and time-travel debugging of any document's journey
through the graph.

## Human-in-the-Loop (HITL) Protocol

LangGraph's `interrupt()` mechanism provides built-in pause/resume for human
intervention. The graph pauses execution, persists state to the checkpoint store,
and waits for external input before resuming.

**Mandatory Interrupt Points**:

| Trigger | State | Resume Condition |
|---|---|---|
| OCR field confidence < 0.85 | `Needs_Review` | Human reviewer corrects or approves field values. Graph resumes with updated `ContraState`. |
| Duplicate bank transactions (LOCKED) | `Human_Review` | Human selects the correct transaction or rejects all. Graph resumes with selection in state. |
| Amount delta ≠ $0.00 | `Exception_Review` | Human confirms override with Fee Logic justification, or rejects. |

**HITL Rules**:

- Interrupt state MUST be persisted via LangGraph checkpointing. A server restart
  MUST NOT lose pending reviews.
- The `Command` object used to resume MUST include the reviewer identity and a
  rationale string. Anonymous resumes are PROHIBITED.
- Resumed state updates MUST be validated against the same gate checks as
  automated transitions. A human override does not bypass gate logic — it provides
  the missing data that enables the gate to pass.
- All HITL actions (pause, resume, reject) MUST be written to the audit log with
  `agent: "human_reviewer"`.

## Security & Audit Trail

**Mandatory Reasoning Log**: Before completing any state transition, every agent
MUST write a structured reasoning entry to the audit database. The entry MUST
include:

```json
{
  "agent": "<agent_name>",
  "timestamp": "<UTC ISO-8601>",
  "input_hash": "<sha256 of input payload>",
  "output_hash": "<sha256 of output payload>",
  "state_from": "<prior state>",
  "state_to": "<new state or error route>",
  "decision": "<MATCHED | PENDING | FLAGGED | LOCKED | ERROR>",
  "rationale": "<plain-English explanation — e.g., 'Bank Ref ID REF-789 matched; name similarity 0.94 (threshold met)'>",
  "confidence_scores": { "<field>": <score> }
}
```

**Immutability**: Audit log entries are append-only. No agent, service, or background
job may update or delete a prior entry. Any system that permits mutation of audit
entries is non-compliant.

**PII Exclusion**: Full PII values MUST NOT appear in any audit log entry. Only
masked tokens (e.g., `****1234`) are permitted.

**Compliance Gate on PRs**: Every pull request that modifies agent logic MUST include
a "Constitution Compliance" checklist item in the PR description confirming which
principles were reviewed.

## Tech Stack Constraints

**Backend**: Python 3.12+, FastAPI (latest stable). Dependency isolation via
`venv` — no global pip installs. All dependencies pinned to exact versions in
`requirements.txt`.

**Frontend**: Angular (latest stable LTS), TypeScript in strict mode. `any` types
are FORBIDDEN in production code. Angular standalone components are the default
pattern.

**Agent Framework**: LangGraph is the orchestration layer for all agent workflows.
Agents are implemented as **LangGraph node functions** operating on a shared
`ContraState` TypedDict. The graph definition lives in `backend/src/graph/pipeline.py`.

**LLM Adapter Boundary**: All LLM provider calls MUST go through a LangChain
`BaseChatModel` implementation configured in `backend/src/adapters/llm_adapter.py`.
The adapter wraps the provider-specific model (OpenAI, Anthropic, etc.) and exposes
it as a standard LangChain chat model. Node functions receive the model via state or
dependency injection — they MUST NOT import vendor SDKs directly. Switching providers
MUST require only configuration changes in the adapter, not code changes in nodes.

**API Contract**: All backend endpoints MUST be documented via OpenAPI (FastAPI
auto-generation). The Angular frontend MUST consume only typed DTOs generated from
the OpenAPI schema. Hand-written type interfaces that duplicate schema types are
FORBIDDEN.

**Persistence Layer**: SQLAlchemy 2.x ORM using the code-first (declarative)
approach. All ORM models live in `backend/src/db/models.py`. The database engine
and session factory live in `backend/src/db/engine.py`. Database connection is
configured via the `DATABASE_URL` environment variable.

- **Database**: Microsoft SQL Server, accessed via `pyodbc` with ODBC Driver 17.
- **ORM Pattern**: Code-first — ORM models are the source of truth for the schema.
  Table creation and migrations use `Base.metadata.create_all()` or Alembic.
- **Session Management**: FastAPI dependency injection via `get_db()`. One session
  per request. Sessions MUST be closed after use (handled by the dependency).
- **No Raw SQL in Business Logic**: All database access MUST go through SQLAlchemy
  ORM queries. Raw SQL strings in agent code or route handlers are FORBIDDEN.
  Exceptions require a comment justifying the bypass.
- **Connection String**: `DATABASE_URL` defaults to
  `mssql+pyodbc://sa:Admin@1234@localhost:1433/contra?driver=ODBC+Driver+17+for+SQL+Server`
  in development. Production credentials MUST be injected via environment variables
  — never hardcoded.

**Package Policy**: Latest stable packages. Floating version ranges (e.g., `>=`,
`^`, `~`) are FORBIDDEN in `requirements.txt` and `package.json` for production
dependencies.

## Deployment

**Docker Compose** is the standard deployment method. The root `docker-compose.yml`
orchestrates all services.

### Services

| Service | Image / Build | Purpose |
|---|---|---|
| `db` | `mcr.microsoft.com/mssql/server:2022-latest` | MSSQL database |
| `backend` | Built from `backend/Dockerfile` | FastAPI backend |

### Backend Container Lifecycle

1. The entrypoint script (`backend/entrypoint.sh`) runs automatically on container start.
2. It creates the `contra` database in MSSQL if it does not exist.
3. It runs `alembic upgrade head` to apply all pending migrations.
4. It starts uvicorn on port 8000.

### Deployment Rules

- **No hardcoded credentials in images**: All secrets (`DATABASE_URL`, `LLM_API_KEY`,
  `MSSQL_SA_PASSWORD`) MUST be passed via environment variables or Docker secrets.
  Baking credentials into Dockerfile or source code is PROHIBITED.
- **Migrations are automatic**: The entrypoint MUST run Alembic migrations before
  starting the application. Manual migration steps are not acceptable in containerized
  environments.
- **Health checks**: The `db` service MUST include a health check. The `backend`
  service MUST NOT start until the database is healthy (`depends_on` with
  `condition: service_healthy`).
- **CORS configuration**: CORS allowed origins are configured via the `CORS_ORIGINS`
  environment variable (comma-separated list). Default: `http://localhost:4200`.
- **Volume persistence**: Database data MUST be stored in a named Docker volume
  (`mssql_data`) to survive container restarts.

## Governance

**Supremacy**: This constitution supersedes all feature specs, implementation plans,
PRs, and verbal agreements. In any conflict, this document is the authority.

**Amendment Procedure**: Any amendment requires: (1) a written proposal stating the
change and rationale, (2) a version bump per the policy below, (3) an update to the
Sync Impact Report comment at the top of this file. Undocumented amendments are
invalid.

**Versioning Policy**:
- MAJOR: Removal or redefinition of a Core Principle, Agent Protocol, or State
  Machine gate.
- MINOR: Addition of a new principle, agent protocol, state, or top-level section.
- PATCH: Clarifications, wording corrections, formatting, non-semantic refinements.

**Compliance Review**: Every sprint MUST include a constitution compliance check as a
non-optional gate before any feature is marked Done. The state machine gate logic in
`backend/src/agents/auditor.py` is the canonical enforcement implementation. Tests
covering each gate MUST run on every CI build.

**Version**: 2.2.0 | **Ratified**: 2026-03-23 | **Last Amended**: 2026-03-23

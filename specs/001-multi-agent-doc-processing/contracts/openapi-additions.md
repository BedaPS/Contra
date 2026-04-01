# API Contract: Multi-Agent Document Processing System

**Branch**: `001-multi-agent-doc-processing`  
**Date**: 2026-03-25  
**Format**: OpenAPI (FastAPI auto-generated) — this document describes the additions; the canonical contract is the running OpenAPI schema at `/openapi.json`.

---

## New Endpoints

The following endpoints are added to `backend/src/api/routes.py`. All are prefixed `/api/v1` by the `APIRouter`.

---

### `POST /api/v1/runs`

**Purpose**: Trigger a new pipeline batch run. Creates a `BatchRun`, scans the configured source folder, enqueues all discovered files for async processing, and begins streaming AG-UI events.

**Request Body**: None (empty body). All configuration is read from the settings store (`source_directory`, `work_directory`, `output_directory`, `LLM_PROVIDER`, `LLM_MODEL`).

**Response `200 OK`**:
```json
{
  "batch_id": "3f6c1a9e-4b2d-47f0-b8e3-2c1a9eb3dc21",
  "total_files": 12,
  "status": "In Progress"
}
```

**Schema**: `RunStartedResponse`
```
batch_id:     str   — GUID of the new BatchRun
total_files:  int   — number of files discovered in source folder
status:       str   — always "In Progress" on success
```

**Error responses**:
- `400 Bad Request` — source directory is not configured or does not exist
- `409 Conflict` — a run is already In Progress (one concurrent run allowed)
- `500 Internal Server Error` — unexpected failure

---

### `GET /api/v1/runs`

**Purpose**: List all batch runs, newest first.

**Response `200 OK`**: Array of `BatchRunSummary`
```json
[
  {
    "batch_id": "3f6c1a9e-4b2d-47f0-b8e3-2c1a9eb3dc21",
    "triggered_at": "2026-03-25T10:00:00Z",
    "completed_at": "2026-03-25T10:04:30Z",
    "total_files": 12,
    "total_records": 17,
    "status": "Completed"
  }
]
```

---

### `GET /api/v1/runs/{batch_id}`

**Purpose**: Run detail including per-file status.

**Path param**: `batch_id` — GUID string

**Response `200 OK`**: `BatchRunDetail`
```json
{
  "batch_id": "3f6c1a9e-4b2d-47f0-b8e3-2c1a9eb3dc21",
  "triggered_at": "2026-03-25T10:00:00Z",
  "completed_at": "2026-03-25T10:04:30Z",
  "total_files": 12,
  "total_records": 17,
  "status": "Completed",
  "run_records": [
    {
      "record_id": "a1b2c3d4-...",
      "source_filename": "invoice_001.pdf",
      "guid_filename": "f7e3a2b1_invoice_001.pdf",
      "status": "Completed",
      "record_count": 2,
      "started_at": "2026-03-25T10:00:05Z",
      "completed_at": "2026-03-25T10:00:22Z"
    }
  ]
}
```

**Error responses**:
- `404 Not Found` — `batch_id` does not exist

---

### `GET /api/v1/results`

**Purpose**: List extracted payment records. Filterable by batch and validation status.

**Query parameters**:

| Param | Type | Default | Notes |
|---|---|---|---|
| `batch_id` | `str` | — | Filter by batch GUID |
| `doc_type` | `str` | — | Filter by `email`\|`remittance`\|`receipt`\|`unknown` |
| `validation_status` | `str` | — | Filter by `Valid`\|`Review Required`\|`Extraction Failed` |
| `confidence_min` | `float` | 0.0 | Filter records where overall_confidence ≥ value |
| `confidence_max` | `float` | 1.0 | Filter records where overall_confidence ≤ value |
| `skip` | `int` | 0 | Pagination offset |
| `limit` | `int` | 100 | Max 500 |

**Response `200 OK`**: Array of `PaymentRecordResponse`
```json
[
  {
    "id": 42,
    "run_record_id": "a1b2c3d4-...",
    "batch_id": "3f6c1a9e-...",
    "customer_name": "ACME Corporation",
    "account_number": "****4321",
    "payee": "Contra Ltd",
    "payment_id": "PAY-2026-001",
    "payment_method": "EFT",
    "payment_date": "2026-03-20",
    "invoice_number": "INV-0042",
    "reference_doc_number": "REF-8841",
    "amount_paid": 15750.0,
    "currency": "ZAR",
    "deductions": 0.0,
    "deduction_type": null,
    "notes": null,
    "validation_status": "Valid",
    "confidence_scores": {
      "customer_name": 0.97,
      "amount_paid": 0.99,
      "payment_date": 0.96
    },
    "llm_provider": "openai",
    "llm_model": "gpt-4o",
    "source_filename": "invoice_001.pdf",
    "doc_type": "remittance",
    "created_at": "2026-03-25T10:00:22Z"
  }
]
```

---

### `GET /api/v1/runs/{batch_id}/stream`

**Purpose**: Server-Sent Events (SSE) endpoint for real-time batch processing progress. Angular connects via `EventSource` after receiving `batch_id` from `POST /api/runs`.

**Path param**: `batch_id` — must be an active or recently completed batch

**Response**: `text/event-stream` — sequence of SSE frames until `BATCH_COMPLETED`.

**AG-UI Event Payloads**:

#### `BATCH_STARTED`
```json
{
  "type": "BATCH_STARTED",
  "timestamp": 1711361200.123,
  "batch_id": "3f6c1a9e-...",
  "total_files": 12
}
```

#### `FILE_STARTED`
```json
{
  "type": "FILE_STARTED",
  "timestamp": 1711361205.456,
  "batch_id": "3f6c1a9e-...",
  "run_record_id": "a1b2c3d4-...",
  "source_filename": "invoice_001.pdf",
  "file_index": 1,
  "total_files": 12
}
```

#### `FILE_COMPLETED`
```json
{
  "type": "FILE_COMPLETED",
  "timestamp": 1711361222.789,
  "batch_id": "3f6c1a9e-...",
  "run_record_id": "a1b2c3d4-...",
  "source_filename": "invoice_001.pdf",
  "record_count": 2,
  "validation_summary": {
    "Valid": 2,
    "Review Required": 0,
    "Extraction Failed": 0
  }
}
```

#### `FILE_FAILED`
```json
{
  "type": "FILE_FAILED",
  "timestamp": 1711361222.789,
  "batch_id": "3f6c1a9e-...",
  "run_record_id": "a1b2c3d4-...",
  "source_filename": "broken_scan.pdf",
  "error": "All 14 extracted fields are null"
}
```

#### `BATCH_COMPLETED`
```json
{
  "type": "BATCH_COMPLETED",
  "timestamp": 1711361470.000,
  "batch_id": "3f6c1a9e-...",
  "total_files": 12,
  "total_records": 17,
  "status_summary": {
    "Valid": 12,
    "Review Required": 3,
    "Extraction Failed": 2
  }
}
```

**Behaviour**: The SSE connection is held open until `BATCH_COMPLETED` is emitted, then the stream closes. If the client disconnects and reconnects, missed events are NOT replayed (the UI re-fetches current state via `GET /api/runs/{batch_id}`).

---

## Modified Endpoints

### `GET /api/v1/settings/llm` and `PUT /api/v1/settings/llm`

Both responses now include `output_directory: str`.

---

## Angular Frontend Service Interface

The Angular `RunsService` (`frontend/src/app/core/services/runs.service.ts`) exposes:

```typescript
// Trigger new run
startRun(): Observable<RunStartedResponse>

// List all runs
listRuns(): Observable<BatchRunSummary[]>

// Get run detail
getRun(batchId: string): Observable<BatchRunDetail>

// Get payment records
getResults(filters: ResultsFilter): Observable<PaymentRecordResponse[]>
```

The `AgUiEventService` is extended with a `connectToBatch(batchId: string): void` method that replaces the existing `startRun()` for the new pipeline, connecting to `/api/v1/runs/{batch_id}/stream` instead of `/api/v1/agents/stream`.

New AG-UI event types are added to `ag-ui.models.ts`.

---

## TypeScript Interface Additions (`run.models.ts`)

```typescript
export interface RunStartedResponse {
  batch_id: string;
  total_files: number;
  status: string;
}

export interface RunRecordSummary {
  record_id: string;
  source_filename: string;
  guid_filename: string;
  status: string;
  record_count: number;
  started_at: string;
  completed_at: string | null;
}

export interface BatchRunSummary {
  batch_id: string;
  triggered_at: string;
  completed_at: string | null;
  total_files: number;
  total_records: number;
  status: string;
}

export interface BatchRunDetail extends BatchRunSummary {
  run_records: RunRecordSummary[];
}

export interface PaymentRecordResponse {
  id: number;
  run_record_id: string;
  batch_id: string;
  customer_name: string | null;
  account_number: string | null;
  payee: string | null;
  payment_id: string | null;
  payment_method: string | null;
  payment_date: string | null;
  invoice_number: string | null;
  reference_doc_number: string | null;
  amount_paid: number | null;
  currency: string | null;
  deductions: number | null;
  deduction_type: string | null;
  notes: string | null;
  validation_status: string;
  confidence_scores: Record<string, number>;
  llm_provider: string;
  llm_model: string;
  source_filename: string;
  doc_type: string;
  created_at: string;
}

export interface ResultsFilter {
  batch_id?: string;
  doc_type?: string;
  validation_status?: string;
  confidence_min?: number;
  confidence_max?: number;
  skip?: number;
  limit?: number;
}

// AG-UI event type additions
export interface BatchStartedEvent extends AgUiEvent {
  type: 'BATCH_STARTED';
  batch_id: string;
  total_files: number;
}

export interface FileStartedEvent extends AgUiEvent {
  type: 'FILE_STARTED';
  batch_id: string;
  run_record_id: string;
  source_filename: string;
  file_index: number;
  total_files: number;
}

export interface FileCompletedEvent extends AgUiEvent {
  type: 'FILE_COMPLETED';
  batch_id: string;
  run_record_id: string;
  source_filename: string;
  record_count: number;
  validation_summary: Record<string, number>;
}

export interface FileFailedEvent extends AgUiEvent {
  type: 'FILE_FAILED';
  batch_id: string;
  run_record_id: string;
  source_filename: string;
  error: string;
}

export interface BatchCompletedEvent extends AgUiEvent {
  type: 'BATCH_COMPLETED';
  batch_id: string;
  total_files: number;
  total_records: number;
  status_summary: Record<string, number>;
}
```

# Data Model: Multi-Agent Document Processing System

**Branch**: `001-multi-agent-doc-processing`  
**Date**: 2026-03-25  
**Derived from**: `spec.md` (Clarified), `research.md`

---

## 1. New Database Tables (SQLAlchemy ORM)

All three new models are added to `backend/src/db/models.py`. A new Alembic migration adds the tables.

### 1.1 `batch_runs` — `BatchRunModel`

One row per UI-triggered pipeline run.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `batch_id` | `String(64)` | PK | GUID string `uuid4` |
| `triggered_at` | `DateTime(tz=True)` | NOT NULL | UTC creation time |
| `completed_at` | `DateTime(tz=True)` | nullable | Set when all files finish |
| `total_files` | `Integer` | NOT NULL, default 0 | Count of files discovered |
| `total_records` | `Integer` | NOT NULL, default 0 | Count of PaymentRecords produced |
| `status` | `String(32)` | NOT NULL, default `'In Progress'` | `'In Progress'` \| `'Completed'` \| `'Failed'` |

**Indexes**: `ix_batch_runs_status` on `status`.

---

### 1.2 `run_records` — `RunRecordModel`

One row per file within a `BatchRun`.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `record_id` | `String(64)` | PK | GUID string `uuid4` |
| `batch_id` | `String(64)` | NOT NULL, FK → `batch_runs.batch_id` | |
| `source_filename` | `String(512)` | NOT NULL | Original filename |
| `work_path` | `String(1024)` | NOT NULL | Full path in work folder |
| `guid_filename` | `String(576)` | NOT NULL | `{guid}_{original_filename}` |
| `started_at` | `DateTime(tz=True)` | NOT NULL | |
| `completed_at` | `DateTime(tz=True)` | nullable | |
| `record_count` | `Integer` | NOT NULL, default 0 | PaymentRecords extracted |
| `status` | `String(32)` | NOT NULL, default `'Pending'` | `'Pending'` \| `'Processing'` \| `'Completed'` \| `'Failed'` |

**Indexes**: `ix_run_records_batch_id` on `batch_id`, `ix_run_records_status` on `status`.

---

### 1.3 `payment_records` — `PaymentRecordModel`

One row per extracted payment amount. Many rows per `run_record`, many per `batch_run`.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `Integer` | PK, autoincrement | |
| `run_record_id` | `String(64)` | NOT NULL, FK → `run_records.record_id` | |
| `batch_id` | `String(64)` | NOT NULL | Denormalised for efficient batch-level queries |
| `page_number` | `Integer` | nullable | 1-based page index where amount was found; supports `(amount_paid, page_number)` dedup per FR-006 |
| `customer_name` | `String(512)` | nullable | Extracted field |
| `account_number` | `String(128)` | nullable | Extracted field — shown in output, NOT in audit logs |
| `payee` | `String(512)` | nullable | Extracted field |
| `payment_id` | `String(128)` | nullable | Extracted field |
| `payment_method` | `String(64)` | nullable | Normalised: `EFT` \| `CASH` \| `CHEQUE` \| `DIRECT_DEPOSIT` \| `CARD` |
| `payment_date` | `String(32)` | nullable | Normalised: `YYYY-MM-DD` |
| `invoice_number` | `String(128)` | nullable | Extracted field |
| `reference_doc_number` | `String(128)` | nullable | Extracted field |
| `amount_paid` | `Float` | nullable | Normalised: float |
| `currency` | `String(8)` | nullable | Normalised: ISO 4217 (e.g., `ZAR`, `USD`) |
| `deductions` | `Float` | nullable | Normalised: float |
| `deduction_type` | `String(128)` | nullable | Extracted field |
| `notes` | `Text` | nullable | Extracted field |
| `validation_status` | `String(32)` | NOT NULL | `'Valid'` \| `'Review Required'` \| `'Extraction Failed'` |
| `confidence_scores` | `Text` | NOT NULL | JSON: `{"field_name": 0.92, ...}` |
| `overall_confidence` | `Float` | NOT NULL, default 0.0 | Mean of all `confidence_scores` values; backing column for `confidence_min`/`confidence_max` query filters |
| `llm_provider` | `String(64)` | NOT NULL | e.g. `openai` |
| `llm_model` | `String(128)` | NOT NULL | e.g. `gpt-4o` |
| `source_filename` | `String(512)` | NOT NULL | Denormalised for direct lookup |
| `doc_type` | `String(32)` | NOT NULL | `email` \| `remittance` \| `receipt` \| `unknown` |
| `created_at` | `DateTime(tz=True)` | NOT NULL | |

**Indexes**: `ix_payment_records_batch_id`, `ix_payment_records_validation_status`, `ix_payment_records_run_record_id`.

---

## 2. Pydantic Schemas (API Serialisation)

Located in `backend/src/schemas/`.

### 2.1 `payment_record.py` (new file)

```python
class PaymentRecordCreate(BaseModel):
    """Internal model — written after LangGraph validation node."""
    run_record_id: str
    batch_id: str
    # 14 extracted fields (all nullable)
    customer_name: str | None
    account_number: str | None
    payee: str | None
    payment_id: str | None
    payment_method: str | None
    payment_date: str | None
    invoice_number: str | None
    reference_doc_number: str | None
    amount_paid: float | None
    currency: str | None
    deductions: float | None
    deduction_type: str | None
    notes: str | None
    page_number: int | None
    overall_confidence: float       # Mean of confidence_scores; backing field for confidence_min/confidence_max filters
    # Validation
    validation_status: str          # 'Valid' | 'Review Required' | 'Extraction Failed'
    confidence_scores: dict[str, float]
    llm_provider: str
    llm_model: str
    source_filename: str
    doc_type: str

class PaymentRecordResponse(PaymentRecordCreate):
    """API response — includes DB id and created_at."""
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
```

### 2.2 `run.py` (new file)

```python
class RunStartedResponse(BaseModel):
    batch_id: str
    total_files: int
    status: str

class RunRecordSummary(BaseModel):
    record_id: str
    source_filename: str
    guid_filename: str
    status: str
    record_count: int
    started_at: datetime
    completed_at: datetime | None
    model_config = ConfigDict(from_attributes=True)

class BatchRunSummary(BaseModel):
    batch_id: str
    triggered_at: datetime
    completed_at: datetime | None
    total_files: int
    total_records: int
    status: str
    model_config = ConfigDict(from_attributes=True)

class BatchRunDetail(BatchRunSummary):
    run_records: list[RunRecordSummary]
```

### 2.3 `llm_settings.py` (modify existing)

Add `output_directory: str` field to both `LLMSettings` and `LLMSettingsResponse`.

---

## 3. LangGraph State

### 3.1 `DocPipelineState` (new TypedDict)

Located in `backend/src/graph/doc_pipeline/state.py`. This is the per-file state flowing through the doc processing graph.

```python
class PaymentRecordDict(TypedDict, total=False):
    """Extracted payment record — in-flight before DB write."""
    customer_name: str | None
    account_number: str | None
    payee: str | None
    payment_id: str | None
    payment_method: str | None
    payment_date: str | None
    invoice_number: str | None
    reference_doc_number: str | None
    amount_paid: float | None
    currency: str | None
    deductions: float | None
    deduction_type: str | None
    notes: str | None
    page_number: int | None
    confidence_scores: dict[str, float]
    validation_status: str

class DocPipelineState(TypedDict, total=False):
    # Run context
    batch_id: Annotated[str, _replace]
    run_record_id: Annotated[str, _replace]

    # File paths
    source_file_path: Annotated[str, _replace]
    work_file_path: Annotated[str, _replace]
    guid_filename: Annotated[str, _replace]

    # Classifier output
    doc_type: Annotated[str | None, _replace]         # 'email'|'remittance'|'receipt'|'unknown'
    prompt_config: Annotated[dict | None, _replace]   # loaded YAML config

    # Extractor input
    page_images: Annotated[list[str], _replace]        # base64 PNG per page

    # Extractor → Normaliser → Validator chain
    raw_records: Annotated[list[PaymentRecordDict], _replace]        # post-extraction
    normalised_records: Annotated[list[PaymentRecordDict], _replace]  # post-normalisation
    validated_records: Annotated[list[PaymentRecordDict], _replace]   # post-validation with status

    # Retry tracking
    extraction_attempts: Annotated[int, _replace]    # 0-based; max 3 per spec

    # Error tracking
    error: Annotated[str | None, _replace]
    error_type: Annotated[str | None, _replace]  # 'parse_error'|'rate_limit'|'all_null'
```

---

## 4. File-Based Data (non-DB)

### 4.1 `accuracy.jsonl` — Accuracy Log

Written to `{output_directory}/accuracy.jsonl`. One JSON line per processed document (not per PaymentRecord).

```json
{
  "timestamp": "2026-03-25T10:00:00Z",
  "source_filename": "invoice_001.pdf",
  "doc_type": "remittance",
  "validation_status": "Valid",
  "overall_confidence": 0.94,
  "fields_extracted": 12,
  "null_fields": 2,
  "extraction_attempts": 1,
  "llm_provider": "openai",
  "llm_model": "gpt-4o"
}
```

### 4.2 `results.xlsx` — Excel Output

Written to `{output_directory}/results.xlsx`. Two sheets:

**Sheet 1 — "Payment Records"**: All records, columns in order:
`Customer Name`, `Account Number`, `Payee`, `Payment ID`, `Payment Method`, `Payment Date`, `Invoice Number`, `Reference Doc Number`, `Amount Paid`, `Currency`, `Deductions`, `Deduction Type`, `Notes`, `Validation Status`, `Confidence Score`, `LLM Model`, `Source File`

Row colour-coding via `openpyxl` fill:
- Green (`#C6EFCE`) — `Valid`
- Amber (`#FFEB9C`) — `Review Required`
- Red (`#FFC7CE`) — `Extraction Failed`

**Sheet 2 — "Review Required"**: Same columns, filtered to `Review Required` and `Extraction Failed` rows only.

### 4.3 `PromptConfig` YAML Schema

One YAML file per doc type in `backend/src/prompt_configs/`. Example:

```yaml
# remittance.yaml
context_hint: |
  This document is a remittance advice. Extract all payment details precisely.

field_hints:
  customer_name: "The name of the customer or payer as printed on the document."
  amount_paid: "The total payment amount as a numeric value. Critical field."
  payment_date: "The date of payment in any format — will be normalised to YYYY-MM-DD."
  # ... (one per field)

confidence_thresholds:
  customer_name: 0.75
  account_number: 0.80
  amount_paid: 0.90   # Must be >= 0.85 per constitution alignment (see research.md §11)
  payment_date: 0.80
  currency: 0.75
  # Fields not listed inherit the default: 0.70

required_fields:
  - amount_paid
```

---

## 5. Settings Model Extension

`LLMSettings` in `backend/src/schemas/llm_settings.py` gets:

```python
output_directory: str = Field(
    default="",
    description="Output directory for results.xlsx and accuracy.jsonl.",
)
```

`settings_store.py` gets `OUTPUT_DIRECTORY` env var fallback.

---

## 6. State Transitions — DocPipelineState

```
File discovered in source folder
          │
          ▼
  [classifier_node]
  Reads page 1 image → LLM classify → sets doc_type, loads prompt_config
          │ success
          ▼
  [extractor_node]
  Renders all pages → base64 images → LLM extract per-page
  Produces raw_records (one per distinct amount)
  Retry loop: parse failures → re-invoke LLM (max 3 attempts)
          │ success / partial
          ▼
  [normaliser_node]
  Normalise dates → YYYY-MM-DD
  Normalise amounts → float
  Normalise currencies → ISO 4217
  Normalise payment_method → canonical form
          │
          ▼
  [validator_node]
  Per-field confidence vs. YAML threshold
  Assign validation_status per record:
    → 'Extraction Failed' if amount_paid null OR below threshold
    → 'Review Required' if any other field below threshold
    → 'Valid' otherwise
          │
          ▼
  [excel_writer_node]
  Persist records → DB (PaymentRecordModel batch insert)
  Move failed files → work_dir/failed/
  Append → accuracy.jsonl
  (Re-)write results.xlsx (all records for this batch_id)
  Update RunRecord.status → 'Completed' | 'Failed'
  Update BatchRun.total_records
          │
          ▼
         END (per file)

After all files complete:
  BatchRun.status → 'Completed' | 'Failed'
  BatchRun.completed_at → now()
```

**Error routing**:
- Classifier fails → `error_type = 'classify_error'` → skip file, mark `RunRecord` Failed
- All-null extraction → `error_type = 'all_null'` → `Extraction Failed` record, no retry
- 3 parse failures → `error_type = 'parse_error'` → `Extraction Failed` record
- Rate limit → exponential backoff 5s → 15s → 45s → fail

---

## 7. Alembic Migration

New file: `backend/alembic/versions/{revision}_add_doc_processing_tables.py`

Creates three tables: `batch_runs`, `run_records`, `payment_records`. Foreign key constraints:
- `run_records.batch_id → batch_runs.batch_id`
- `payment_records.run_record_id → run_records.record_id`

All indexes as listed in §1.1–1.3.

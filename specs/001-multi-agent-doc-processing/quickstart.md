# Quickstart: Multi-Agent Document Processing System

**Branch**: `001-multi-agent-doc-processing`  
**Audience**: Developer setting up the feature end-to-end for local testing

---

## Prerequisites

- Docker Desktop running (for MSSQL + backend)
- OR Python 3.12 venv for local backend development
- Node.js 20+ for Angular
- A supported LLM provider API key (OpenAI, Anthropic, or Gemini) — OR use `stub` provider for a no-op test

---

## Step 1: Configure Environment

Copy `.env.example` (if present) or set these environment variables before starting the backend:

```env
# LLM Provider
LLM_PROVIDER=openai           # openai | anthropic | gemini | stub
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o              # Must be a vision-capable model

# Folder paths (create these directories)
SOURCE_DIRECTORY=/tmp/contra/source
WORK_DIRECTORY=/tmp/contra/work
OUTPUT_DIRECTORY=/tmp/contra/output
```

Or set them via the Settings UI (`http://localhost:4200/settings`) after starting the application.

---

## Step 2: Prepare Sample Documents

Create the source directory and place 3–5 test payment documents:

```
/tmp/contra/source/
├── remittance_001.pdf
├── invoice_scan.jpg
└── payment_receipt.png
```

Supported formats: `.pdf`, `.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif`, `.bmp`, `.webp`

---

## Step 3: Start the Backend

**Docker (recommended)**:
```bash
cd c:\GitHub\Contra
docker compose up --build
```

The entrypoint automatically:
1. Creates the `contra` database
2. Runs Alembic migrations (adds `batch_runs`, `run_records`, `payment_records` tables)
3. Starts uvicorn on port 8000

**Local (no Docker)**:
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.api.main:app --reload
```

---

## Step 4: Verify Backend Health

```bash
curl http://localhost:8000/api/v1/health
# → {"status": "ok"}
```

Check OpenAPI docs at `http://localhost:8000/docs` — confirm the `/runs` and `/results` endpoints appear.

---

## Step 5: Start the Angular Frontend

```bash
cd frontend
npm ci
npm start
# → Angular dev server at http://localhost:4200
```

---

## Step 6: Run the Pipeline from the UI

1. Open `http://localhost:4200`
2. Navigate to **Run History** (`/runs`)
3. Verify the source folder path is configured in **Settings** (`/settings`)
4. Click **Run Pipeline**
5. Watch the live progress indicator: `1 of 3 files processed...`
6. When progress shows all files complete, the run history updates to `Completed`

---

## Step 7: Verify Outputs

**Database records**:
```sql
SELECT * FROM batch_runs ORDER BY triggered_at DESC;
SELECT * FROM run_records WHERE batch_id = '<your-batch-id>';
SELECT * FROM payment_records WHERE batch_id = '<your-batch-id>';
```

**Files in output directory**:
```
/tmp/contra/output/
├── results.xlsx          ← Colour-coded Excel: green=Valid, amber=Review, red=Failed
└── accuracy.jsonl        ← One JSON line per processed document
```

**Excel validation**: Open `results.xlsx` — confirm:
- Sheet 1 "Payment Records" has one row per extracted payment amount
- Sheet 2 "Review Required" shows only non-Valid records
- Row colours match validation status

---

## Step 8: View Results in the Angular UI

1. Navigate to **Results** (`/results`)
2. Select the batch run from the dropdown or run history
3. The results table shows all extracted `PaymentRecord` rows
4. Use the filter panel to filter by `Validation Status` = `Review Required`
5. Click a row to expand per-field confidence scores

---

## Step 9: Test Provider Swap (Zero Code Change)

```bash
# Stop backend, change provider in .env, restart
LLM_PROVIDER=anthropic
LLM_MODEL=claude-claude-sonnet-4-5
docker compose restart backend
```

Run the pipeline again. Confirm `accuracy.jsonl` shows `"llm_provider": "anthropic"` in new entries.

---

## Step 10: Add a New Document Type (Zero Code Change)

Create `backend/src/prompt_configs/purchase_order.yaml`:

```yaml
context_hint: |
  This is a purchase order. Extract payment details.

field_hints:
  amount_paid: "The total order value."
  # ... other field hints

confidence_thresholds:
  amount_paid: 0.90

required_fields:
  - amount_paid
```

Place a purchase order document in the source folder and run the pipeline. The classifier will map it to `unknown` (or you can update the classifier prompt to recognise `purchase_order`).

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `400 Bad Request` on Run Pipeline | `source_directory` not set | Configure in Settings UI |
| `409 Conflict` on Run Pipeline | Another run is already in progress | Wait for it to complete |
| All records `Extraction Failed` | LLM provider / model not vision-capable | Use `gpt-4o`, `claude-claude-sonnet-4-5`, or `gemini-2.0-flash` |
| No AG-UI events in UI | SSE connection blocked | Check CORS_ORIGINS includes `http://localhost:4200` |
| `results.xlsx` not created | `output_directory` not set | Configure in Settings UI |
| DB migration failed | Old containers with stale schema | `docker compose down -v` then restart |

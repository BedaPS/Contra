/** Shared mock data for Playwright functional tests. */

export const API_BASE = 'http://localhost:8000/api/v1';

export const BATCH_ID = '3f6c1a9e-4b2d-47f0-b8e3-2c1a9eb3dc21';
export const BATCH_ID_IN_PROGRESS = 'aaaa1111-2222-3333-4444-555566667777';
export const BATCH_ID_FAILED = 'bbbb8888-7777-6666-5555-444433332222';
export const RUN_RECORD_ID = 'a1b2c3d4-1234-5678-abcd-1234567890ab';

// ── Run / Batch mocks ──────────────────────────────────────────────────────

export const MOCK_RUN_STARTED = {
  batch_id: BATCH_ID,
  total_files: 3,
  status: 'In Progress',
};

export const MOCK_BATCH_RUNS = [
  {
    batch_id: BATCH_ID,
    triggered_at: '2026-03-25T10:00:00.000Z',
    completed_at: '2026-03-25T10:04:30.000Z',
    total_files: 3,
    total_records: 4,
    status: 'Completed',
  },
  {
    batch_id: BATCH_ID_IN_PROGRESS,
    triggered_at: '2026-03-24T09:30:00.000Z',
    completed_at: null,
    total_files: 5,
    total_records: 0,
    status: 'In Progress',
  },
  {
    batch_id: BATCH_ID_FAILED,
    triggered_at: '2026-03-23T08:00:00.000Z',
    completed_at: '2026-03-23T08:02:00.000Z',
    total_files: 1,
    total_records: 0,
    status: 'Failed',
  },
];

export const MOCK_BATCH_DETAIL = {
  ...MOCK_BATCH_RUNS[0],
  run_records: [
    {
      record_id: RUN_RECORD_ID,
      source_filename: 'invoice_001.pdf',
      guid_filename: 'f7e3a2b1_invoice_001.pdf',
      status: 'Completed',
      record_count: 2,
      started_at: '2026-03-25T10:00:05.000Z',
      completed_at: '2026-03-25T10:00:22.000Z',
    },
    {
      record_id: 'cccc1234-0000-0000-0000-000000000001',
      source_filename: 'receipt_002.pdf',
      guid_filename: 'a1b2c3d4_receipt_002.pdf',
      status: 'Completed',
      record_count: 1,
      started_at: '2026-03-25T10:00:25.000Z',
      completed_at: '2026-03-25T10:00:40.000Z',
    },
  ],
};

// ── Payment record mocks ───────────────────────────────────────────────────

export const MOCK_PAYMENT_RECORDS = [
  {
    id: 1,
    run_record_id: RUN_RECORD_ID,
    batch_id: BATCH_ID,
    source_filename: 'invoice_001.pdf',
    doc_type: 'remittance',
    page_number: 1,
    customer_name: 'ACME Corporation',
    account_number: '****4321',
    payee: 'Contra Ltd',
    payment_id: 'PAY-2026-001',
    payment_method: 'EFT',
    payment_date: '2026-03-20',
    invoice_number: 'INV-0042',
    reference_doc_number: 'REF-8841',
    amount_paid: 15750.0,
    currency: 'ZAR',
    deductions: 0.0,
    deduction_type: null,
    notes: null,
    validation_status: 'Valid',
    overall_confidence: 0.97,
    confidence_scores: { customer_name: 0.97, amount_paid: 0.99, payment_date: 0.96 },
    llm_provider: 'stub',
    llm_model: 'stub',
    created_at: '2026-03-25T10:00:22.000Z',
  },
  {
    id: 2,
    run_record_id: RUN_RECORD_ID,
    batch_id: BATCH_ID,
    source_filename: 'receipt_002.pdf',
    doc_type: 'receipt',
    page_number: 1,
    customer_name: 'Beta Corp',
    account_number: '****9876',
    payee: 'Contra Ltd',
    payment_id: 'PAY-2026-002',
    payment_method: 'CASH',
    payment_date: '2026-03-21',
    invoice_number: 'INV-0043',
    reference_doc_number: null,
    amount_paid: 500.0,
    currency: 'USD',
    deductions: 50.0,
    deduction_type: 'Early payment',
    notes: null,
    validation_status: 'Review Required',
    overall_confidence: 0.72,
    confidence_scores: { customer_name: 0.70, amount_paid: 0.94, payment_date: 0.63 },
    llm_provider: 'stub',
    llm_model: 'stub',
    created_at: '2026-03-25T10:01:00.000Z',
  },
  {
    id: 3,
    run_record_id: 'cccc1234-0000-0000-0000-000000000001',
    batch_id: BATCH_ID,
    source_filename: 'email_003.pdf',
    doc_type: 'email',
    page_number: 1,
    customer_name: null,
    account_number: null,
    payee: null,
    payment_id: null,
    payment_method: null,
    payment_date: null,
    invoice_number: null,
    reference_doc_number: null,
    amount_paid: null,
    currency: null,
    deductions: null,
    deduction_type: null,
    notes: null,
    validation_status: 'Extraction Failed',
    overall_confidence: 0.0,
    confidence_scores: {},
    llm_provider: 'stub',
    llm_model: 'stub',
    created_at: '2026-03-25T10:02:00.000Z',
  },
];

// ── Settings mock ──────────────────────────────────────────────────────────

export const MOCK_SETTINGS = {
  provider: 'stub',
  api_key_set: false,
  model: 'stub',
  base_url: '',
  temperature: 0.1,
  source_directory: '/tmp/contra/source',
  work_directory: '/tmp/contra/work',
  review_directory: '/tmp/contra/review',
};

// ── SSE stream helpers ─────────────────────────────────────────────────────

/**
 * Build a complete SSE event body string for a 3-file batch.
 * Includes BATCH_STARTED, FILE_STARTED, FILE_COMPLETED (×2), FILE_FAILED (×1),
 * and BATCH_COMPLETED so the Angular service correctly closes the stream.
 */
export function makeSseBody(batchId: string): string {
  const events = [
    { event: 'BATCH_STARTED', batch_id: batchId, total_files: 3 },
    { event: 'FILE_STARTED', batch_id: batchId, filename: 'doc1.pdf', index: 1 },
    { event: 'FILE_COMPLETED', batch_id: batchId, filename: 'doc1.pdf', record_count: 1 },
    { event: 'FILE_STARTED', batch_id: batchId, filename: 'doc2.pdf', index: 2 },
    { event: 'FILE_COMPLETED', batch_id: batchId, filename: 'doc2.pdf', record_count: 2 },
    { event: 'FILE_STARTED', batch_id: batchId, filename: 'doc3.pdf', index: 3 },
    { event: 'FILE_FAILED', batch_id: batchId, filename: 'doc3.pdf', error: 'LLM parse failure' },
    { event: 'BATCH_COMPLETED', batch_id: batchId, total_records: 3 },
  ];
  return events.map(e => `data: ${JSON.stringify(e)}\n\n`).join('');
}

/**
 * SSE body that only sends BATCH_STARTED — useful for testing the "button
 * disabled while running" state where BATCH_COMPLETED never arrives.
 */
export function makeSseBodyRunning(batchId: string): string {
  return `data: ${JSON.stringify({ event: 'BATCH_STARTED', batch_id: batchId, total_files: 3 })}\n\n`;
}

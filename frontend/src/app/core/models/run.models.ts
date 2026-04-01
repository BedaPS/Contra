/**
 * TypeScript interfaces for the Doc Processing Runs API (T031).
 * Mirror the Pydantic schemas in backend/src/schemas/run.py and payment_record.py.
 */

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
  source_filename: string;
  doc_type: string;
  page_number: number;
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
  overall_confidence: number | null;
  confidence_scores: Record<string, number> | string | null;
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

import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  BatchRunDetail,
  BatchRunSummary,
  PaymentRecordResponse,
  ResultsFilter,
  RunStartedResponse,
} from '../models/run.models';

/**
 * Service for the Doc Processing Runs API (T032).
 * Provides startRun(), listRuns(), getRun(batchId), getResults(filters).
 */
@Injectable({ providedIn: 'root' })
export class RunsService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  /** POST /api/v1/runs — trigger a new batch processing run. */
  startRun(): Observable<RunStartedResponse> {
    return this.http.post<RunStartedResponse>(`${this.base}/runs`, {});
  }

  /** GET /api/v1/runs — list all batch runs, newest first. */
  listRuns(): Observable<BatchRunSummary[]> {
    return this.http.get<BatchRunSummary[]>(`${this.base}/runs`);
  }

  /** GET /api/v1/runs/{batchId} — get a single batch run with run records. */
  getRun(batchId: string): Observable<BatchRunDetail> {
    return this.http.get<BatchRunDetail>(`${this.base}/runs/${encodeURIComponent(batchId)}`);
  }

  /** GET /api/v1/results — list PaymentRecords with optional filters. */
  getResults(filters: ResultsFilter = {}): Observable<PaymentRecordResponse[]> {
    let params = new HttpParams();

    if (filters.batch_id) {
      params = params.set('batch_id', filters.batch_id);
    }
    if (filters.doc_type) {
      params = params.set('doc_type', filters.doc_type);
    }
    if (filters.validation_status) {
      params = params.set('validation_status', filters.validation_status);
    }
    if (filters.confidence_min !== undefined) {
      params = params.set('confidence_min', filters.confidence_min.toString());
    }
    if (filters.confidence_max !== undefined) {
      params = params.set('confidence_max', filters.confidence_max.toString());
    }
    if (filters.skip !== undefined) {
      params = params.set('skip', filters.skip.toString());
    }
    if (filters.limit !== undefined) {
      params = params.set('limit', filters.limit.toString());
    }

    return this.http.get<PaymentRecordResponse[]>(`${this.base}/results`, { params });
  }
}

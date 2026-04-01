import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { RunsService } from '../../core/services/runs.service';
import { PaymentRecordResponse, ResultsFilter } from '../../core/models/run.models';

const STATUS_CLASSES: Record<string, string> = {
  'Valid': 'status-valid',
  'Review Required': 'status-review',
  'Extraction Failed': 'status-failed',
};

@Component({
  selector: 'app-results',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="results-page">
      <header class="page-header">
        <div>
          <h1>Payment Records</h1>
          <p class="subtitle">
            @if (batchId()) { Batch: <span class="mono">{{ batchId() }}</span> }
            @else { All batches }
          </p>
        </div>
      </header>

      <!-- Filter panel -->
      <div class="filter-panel">
        <div class="filter-group">
          <label>Validation Status</label>
          <select [(ngModel)]="filterStatus" (ngModelChange)="applyFilters()">
            <option value="">All</option>
            <option value="Valid">Valid</option>
            <option value="Review Required">Review Required</option>
            <option value="Extraction Failed">Extraction Failed</option>
          </select>
        </div>
        <div class="filter-group">
          <label>Doc Type</label>
          <select [(ngModel)]="filterDocType" (ngModelChange)="applyFilters()">
            <option value="">All</option>
            <option value="email">Email</option>
            <option value="remittance">Remittance</option>
            <option value="receipt">Receipt</option>
            <option value="unknown">Unknown</option>
          </select>
        </div>
        <div class="filter-group">
          <label>Min Confidence</label>
          <input type="number" min="0" max="1" step="0.05" [(ngModel)]="filterConfidenceMin" (ngModelChange)="applyFilters()" placeholder="0.0" />
        </div>
        <div class="filter-group">
          <label>Max Confidence</label>
          <input type="number" min="0" max="1" step="0.05" [(ngModel)]="filterConfidenceMax" (ngModelChange)="applyFilters()" placeholder="1.0" />
        </div>
        <button class="btn-clear" (click)="clearFilters()">Clear Filters</button>
      </div>

      @if (errorMessage()) {
        <div class="alert alert-error">{{ errorMessage() }}</div>
      }

      @if (loading()) {
        <div class="loading">Loading results&hellip;</div>
      } @else {
        <div class="table-wrap">
          <table class="results-table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Payee</th>
                <th>Amount</th>
                <th>Currency</th>
                <th>Payment Date</th>
                <th>Method</th>
                <th>Status</th>
                <th>Confidence</th>
                <th>Doc Type</th>
                <th>Source File</th>
              </tr>
            </thead>
            <tbody>
              @for (rec of records(); track rec.id) {
                <tr class="result-row" [class]="rowClass(rec)" (click)="toggleExpand(rec.id)">
                  <td>{{ rec.customer_name ?? '—' }}</td>
                  <td>{{ rec.payee ?? '—' }}</td>
                  <td class="amount">{{ rec.amount_paid !== null ? (rec.amount_paid | number:'1.2-2') : '—' }}</td>
                  <td>{{ rec.currency ?? '—' }}</td>
                  <td>{{ rec.payment_date ?? '—' }}</td>
                  <td>{{ rec.payment_method ?? '—' }}</td>
                  <td>
                    <span class="status-chip" [class]="statusClass(rec.validation_status)">
                      {{ rec.validation_status }}
                    </span>
                  </td>
                  <td>{{ rec.overall_confidence !== null ? (rec.overall_confidence | percent:'1.0-0') : '—' }}</td>
                  <td><span class="doc-type-chip">{{ rec.doc_type }}</span></td>
                  <td class="filename">{{ rec.source_filename }}</td>
                </tr>
                @if (expandedId() === rec.id) {
                  <tr class="expand-row">
                    <td colspan="10">
                      <div class="confidence-grid">
                        <strong>Per-field Confidence Scores</strong>
                        @for (entry of confidenceEntries(rec); track entry.field) {
                          <div class="score-item">
                            <span class="field-name">{{ entry.field }}</span>
                            <span class="score-bar">
                              <span class="score-fill" [style.width]="(entry.score * 100) + '%'"></span>
                            </span>
                            <span class="score-value">{{ entry.score | percent:'1.0-0' }}</span>
                          </div>
                        }
                      </div>
                    </td>
                  </tr>
                }
              } @empty {
                <tr>
                  <td colspan="10" class="empty-state">No records found matching the current filters.</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </div>
  `,
  styles: [`
    .results-page { padding: 1.5rem; }
    .page-header { margin-bottom: 1rem; }
    .subtitle { color: var(--text-secondary, #6b7280); font-size: 0.875rem; margin-top: 0.25rem; }
    .mono { font-family: monospace; font-size: 0.8rem; }
    .filter-panel { display: flex; gap: 1rem; flex-wrap: wrap; align-items: flex-end; margin-bottom: 1rem; padding: 1rem; background: var(--surface, #f9fafb); border-radius: 8px; }
    .filter-group { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.8rem; color: var(--text-secondary, #6b7280); }
    .filter-group select, .filter-group input { padding: 0.4rem 0.6rem; border: 1px solid var(--border, #e5e7eb); border-radius: 4px; font-size: 0.875rem; }
    .btn-clear { padding: 0.4rem 1rem; border: 1px solid var(--border, #e5e7eb); border-radius: 4px; background: none; cursor: pointer; font-size: 0.875rem; align-self: flex-end; }
    .alert-error { background: #fee2e2; color: #b91c1c; padding: 0.75rem 1rem; border-radius: 6px; margin-bottom: 1rem; }
    .loading { text-align: center; padding: 2rem; color: var(--text-secondary, #6b7280); }
    .table-wrap { overflow-x: auto; }
    .results-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
    .results-table th { text-align: left; padding: 0.6rem 0.75rem; border-bottom: 2px solid var(--border, #e5e7eb); color: var(--text-secondary, #6b7280); white-space: nowrap; }
    .results-table td { padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border, #e5e7eb); }
    .result-row { cursor: pointer; }
    .result-row:hover { filter: brightness(0.97); }
    .row-valid { background: #f0fdf4; }
    .row-review { background: #fefce8; }
    .row-failed { background: #fff1f2; }
    .status-chip { padding: 0.2rem 0.5rem; border-radius: 999px; font-size: 0.7rem; font-weight: 600; white-space: nowrap; }
    .status-valid { background: #dcfce7; color: #15803d; }
    .status-review { background: #fef3c7; color: #92400e; }
    .status-failed { background: #fee2e2; color: #b91c1c; }
    .doc-type-chip { padding: 0.15rem 0.5rem; border-radius: 4px; background: #e0e7ff; color: #4338ca; font-size: 0.7rem; }
    .amount { font-variant-numeric: tabular-nums; text-align: right; }
    .filename { font-size: 0.75rem; color: var(--text-secondary, #6b7280); max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .empty-state { text-align: center; color: var(--text-secondary, #6b7280); padding: 2rem; }
    .expand-row { background: var(--surface, #f9fafb); }
    .confidence-grid { padding: 0.75rem 1rem; display: flex; flex-direction: column; gap: 0.4rem; }
    .confidence-grid strong { font-size: 0.8rem; margin-bottom: 0.25rem; }
    .score-item { display: flex; align-items: center; gap: 0.5rem; font-size: 0.75rem; }
    .field-name { width: 160px; flex-shrink: 0; color: var(--text-secondary, #6b7280); }
    .score-bar { flex: 1; height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; }
    .score-fill { display: block; height: 100%; background: #6366f1; border-radius: 4px; }
    .score-value { width: 3rem; text-align: right; }
  `],
})
export class ResultsComponent implements OnInit {
  private readonly runsService = inject(RunsService);
  private readonly route = inject(ActivatedRoute);

  readonly records = signal<PaymentRecordResponse[]>([]);
  readonly loading = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly expandedId = signal<number | null>(null);

  // filter state
  filterStatus = '';
  filterDocType = '';
  filterConfidenceMin: number | null = null;
  filterConfidenceMax: number | null = null;

  readonly batchId = signal<string | null>(null);

  ngOnInit(): void {
    this.route.queryParamMap.subscribe(params => {
      const id = params.get('batch_id');
      this.batchId.set(id);
      this.loadResults();
    });
  }

  loadResults(): void {
    this.loading.set(true);
    const filter: ResultsFilter = {};
    if (this.batchId()) filter.batch_id = this.batchId()!;
    if (this.filterStatus) filter.validation_status = this.filterStatus;
    if (this.filterDocType) filter.doc_type = this.filterDocType;
    if (this.filterConfidenceMin !== null) filter.confidence_min = this.filterConfidenceMin;
    if (this.filterConfidenceMax !== null) filter.confidence_max = this.filterConfidenceMax;
    filter.limit = 500;

    this.runsService.getResults(filter).subscribe({
      next: (data) => {
        this.records.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.errorMessage.set(err?.error?.detail ?? 'Failed to load results.');
        this.loading.set(false);
      },
    });
  }

  applyFilters(): void {
    this.loadResults();
  }

  clearFilters(): void {
    this.filterStatus = '';
    this.filterDocType = '';
    this.filterConfidenceMin = null;
    this.filterConfidenceMax = null;
    this.loadResults();
  }

  toggleExpand(id: number): void {
    this.expandedId.update(existing => (existing === id ? null : id));
  }

  rowClass(rec: PaymentRecordResponse): string {
    switch (rec.validation_status) {
      case 'Valid': return 'row-valid';
      case 'Review Required': return 'row-review';
      default: return 'row-failed';
    }
  }

  statusClass(status: string): string {
    return STATUS_CLASSES[status] ?? 'status-failed';
  }

  confidenceEntries(rec: PaymentRecordResponse): { field: string; score: number }[] {
    if (!rec.confidence_scores) return [];
    let scores: Record<string, number>;
    if (typeof rec.confidence_scores === 'string') {
      try {
        scores = JSON.parse(rec.confidence_scores);
      } catch {
        return [];
      }
    } else {
      scores = rec.confidence_scores;
    }
    return Object.entries(scores).map(([field, score]) => ({ field, score }));
  }
}

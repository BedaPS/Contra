import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { RunsService } from '../../core/services/runs.service';
import { AgUiEventService } from '../../core/services/ag-ui-event.service';
import { BatchRunSummary } from '../../core/models/run.models';

@Component({
  selector: 'app-runs',
  standalone: true,
  imports: [CommonModule, RouterModule],
  template: `
    <div class="runs-page">
      <header class="page-header">
        <div>
          <h1>Run History</h1>
          <p class="subtitle">Trigger document processing batches and monitor progress</p>
        </div>
        <button
          class="btn btn-primary"
          [disabled]="agUiEventService.isBatchRunning()"
          (click)="startRun()"
        >
          @if (agUiEventService.isBatchRunning()) {
            <span class="spinner"></span>
            Running&hellip; ({{ agUiEventService.filesProcessed() }} / {{ agUiEventService.totalBatchFiles() }} files)
          } @else {
            ▶ Run Pipeline
          }
        </button>
      </header>

      @if (errorMessage()) {
        <div class="alert alert-error">{{ errorMessage() }}</div>
      }

      @if (loading()) {
        <div class="loading">Loading runs&hellip;</div>
      } @else {
        <table class="runs-table">
          <thead>
            <tr>
              <th>Batch ID</th>
              <th>Status</th>
              <th>Files</th>
              <th>Records</th>
              <th>Triggered At</th>
              <th>Completed At</th>
            </tr>
          </thead>
          <tbody>
            @for (run of runs(); track run.batch_id) {
              <tr class="run-row" (click)="goToResults(run.batch_id)">
                <td class="mono">{{ run.batch_id | slice:0:8 }}&hellip;</td>
                <td>
                  <span class="status-chip" [class]="'status-' + run.status.toLowerCase().replace(' ', '-')">
                    {{ run.status }}
                  </span>
                </td>
                <td>{{ run.total_files }}</td>
                <td>{{ run.total_records }}</td>
                <td>{{ run.triggered_at | date:'short' }}</td>
                <td>{{ run.completed_at ? (run.completed_at | date:'short') : '—' }}</td>
              </tr>
            } @empty {
              <tr>
                <td colspan="6" class="empty-state">No runs yet. Click "Run Pipeline" to start.</td>
              </tr>
            }
          </tbody>
        </table>
      }
    </div>
  `,
  styles: [`
    .runs-page { padding: 1.5rem; }
    .page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem; }
    .subtitle { color: var(--text-secondary, #6b7280); font-size: 0.875rem; margin-top: 0.25rem; }
    .btn-primary { padding: 0.5rem 1.25rem; background: var(--accent, #6366f1); color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 0.875rem; display: flex; align-items: center; gap: 0.5rem; }
    .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
    .alert-error { background: #fee2e2; color: #b91c1c; padding: 0.75rem 1rem; border-radius: 6px; margin-bottom: 1rem; }
    .runs-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
    .runs-table th { text-align: left; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border, #e5e7eb); color: var(--text-secondary, #6b7280); font-weight: 500; }
    .runs-table td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--border, #e5e7eb); }
    .run-row { cursor: pointer; }
    .run-row:hover { background: var(--surface-hover, #f9fafb); }
    .mono { font-family: monospace; font-size: 0.8rem; }
    .status-chip { padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.75rem; font-weight: 500; }
    .status-completed { background: #dcfce7; color: #15803d; }
    .status-in-progress { background: #fef3c7; color: #92400e; }
    .status-failed { background: #fee2e2; color: #b91c1c; }
    .empty-state { text-align: center; color: var(--text-secondary, #6b7280); padding: 2rem; }
    .loading { text-align: center; padding: 2rem; color: var(--text-secondary, #6b7280); }
    .spinner { display: inline-block; width: 0.75rem; height: 0.75rem; border: 2px solid currentColor; border-top-color: transparent; border-radius: 50%; animation: spin 0.6s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
  `],
})
export class RunsComponent implements OnInit {
  private readonly runsService = inject(RunsService);
  readonly agUiEventService = inject(AgUiEventService);
  private readonly router = inject(Router);

  readonly runs = signal<BatchRunSummary[]>([]);
  readonly loading = signal(false);
  readonly errorMessage = signal<string | null>(null);

  ngOnInit(): void {
    this.loadRuns();
  }

  loadRuns(): void {
    this.loading.set(true);
    this.runsService.listRuns().subscribe({
      next: (data) => {
        this.runs.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.errorMessage.set(err?.error?.detail ?? 'Failed to load runs.');
        this.loading.set(false);
      },
    });
  }

  startRun(): void {
    this.errorMessage.set(null);
    this.runsService.startRun().subscribe({
      next: (response) => {
        this.agUiEventService.connectToBatch(response.batch_id);
        this.loadRuns();
      },
      error: (err) => {
        const detail = err?.error?.detail ?? 'Failed to start run.';
        this.errorMessage.set(detail);
      },
    });
  }

  goToResults(batchId: string): void {
    this.router.navigate(['/results'], { queryParams: { batch_id: batchId } });
  }
}

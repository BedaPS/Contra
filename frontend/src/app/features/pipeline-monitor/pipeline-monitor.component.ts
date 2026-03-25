import { Component, effect, inject, OnInit, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { AgUiEventService } from '../../core/services/ag-ui-event.service';
import { PipelineDocument, PipelineTopologyNode, PipelineTopologyEdge } from '../../core/models/ag-ui.models';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-pipeline-monitor',
  standalone: true,
  imports: [DecimalPipe, FormsModule],
  template: `
    <div class="pipeline-page">
      <header class="page-header">
        <div>
          <h1>Pipeline Monitor</h1>
          <p class="subtitle">Real-time document flow through the reconciliation pipeline</p>
        </div>
        <div class="controls">
          @if (svc.isRunning()) {
            <button class="btn btn-danger" (click)="svc.stopRun()">■ Stop</button>
          } @else {
            <button class="btn btn-primary" (click)="svc.startRun()">▶ Run Pipeline</button>
          }
        </div>
      </header>

      <!-- Dynamic pipeline visualization -->
      @if (topologyLoaded()) {
        <div class="pipeline-track">
          @for (node of pipelineNodes(); track node.id) {
            <div class="stage" [class.completed]="isCompleted(node.label)" [class.active]="isActive(node.label)">
              <div class="stage-dot">
                @if (isCompleted(node.label)) {
                  <span>✓</span>
                } @else if (isActive(node.label)) {
                  <span class="pulse">●</span>
                } @else {
                  <span>○</span>
                }
              </div>
              <div class="stage-label">{{ node.label }}</div>
            </div>
            @if (!$last) {
              <div class="stage-connector" [class.completed]="isCompleted(node.label)"></div>
            }
          }
        </div>

        <!-- Support nodes (human review, error handler) -->
        <div class="support-track">
          @for (node of supportNodes(); track node.id) {
            <div class="support-node">
              <span class="support-dot">◇</span>
              <span class="support-label">{{ node.label }}</span>
            </div>
          }
        </div>
      } @else {
        <div class="pipeline-track loading">
          <span class="loading-text">Loading pipeline topology…</span>
        </div>
      }

      <!-- Spreadsheet Exchange panel — always visible -->
      <div class="exchange-panel" [class.exchange-paused]="spreadsheetReviewPending()">
        <div class="exchange-header">
          <h2>📊 Spreadsheet Exchange</h2>
          @if (spreadsheetReviewPending()) {
            <span class="exchange-badge paused">⏸ Pipeline Paused — Review Required</span>
          } @else if (svc.isRunning() && !latestSpreadsheet()) {
            <span class="exchange-badge building">● Building…</span>
          }
        </div>
        <div class="exchange-body">
          <div class="exchange-card" [class.disabled]="!latestSpreadsheet()">
            <div class="exchange-card-icon">⬇</div>
            <div class="exchange-card-content">
              <h3>Download</h3>
              @if (latestSpreadsheet()) {
                <p class="exchange-filename">{{ latestSpreadsheet() }}</p>
                <button class="btn btn-download" (click)="downloadSpreadsheet(latestSpreadsheet()!)">
                  Download Spreadsheet
                </button>
              } @else {
                <p class="exchange-hint">No spreadsheet available yet — run the pipeline to generate one</p>
              }
            </div>
          </div>
          <div class="exchange-card" [class.disabled]="!latestSpreadsheet()">
            <div class="exchange-card-icon">⬆</div>
            <div class="exchange-card-content">
              <h3>Upload Corrected</h3>
              <p class="exchange-hint">Upload a revised .xlsx to replace the current spreadsheet</p>
              @if (latestSpreadsheet()) {
                <label class="btn btn-upload" for="exchangeUpload">
                  Choose File
                </label>
                <input
                  id="exchangeUpload"
                  type="file"
                  accept=".xlsx"
                  (change)="onFileSelected($event)"
                  style="display:none"
                />
              }
              @if (uploadedFileName()) {
                <span class="upload-name">✓ {{ uploadedFileName() }}</span>
              }
            </div>
          </div>
        </div>
      </div>

      <!-- HITL spreadsheet review -->
      @if (spreadsheetReviewPending()) {
        <div class="review-panel">
          <div class="review-header">
            <span class="review-icon">⏸</span>
            <div>
              <h2>Approve or Reject</h2>
              <p class="review-subtitle">Review the spreadsheet above, then approve to continue matching or reject to stop</p>
            </div>
          </div>

          <div class="review-form">
            <div class="form-group">
              <label for="reviewerId">Reviewer ID</label>
              <input id="reviewerId" type="text" [(ngModel)]="reviewerId" placeholder="e.g. jane.doe" />
            </div>
            <div class="form-group">
              <label for="reviewRationale">Rationale</label>
              <input id="reviewRationale" type="text" [(ngModel)]="reviewRationale" placeholder="Optional note" />
            </div>
          </div>

          <div class="review-buttons">
            <button class="btn btn-approve" (click)="approveSpreadsheet()" [disabled]="!reviewerId">
              ✓ Approve &amp; Continue
            </button>
            <button class="btn btn-reject" (click)="rejectSpreadsheet()" [disabled]="!reviewerId">
              ✗ Reject
            </button>
          </div>
        </div>
      }

      @if (svc.isRunning() || svc.messages().length > 0) {
        <div class="live-feed">
          <h2>
            @if (svc.isRunning()) {
              <span class="live-dot"></span>
            }
            Agent Stream
          </h2>
          <div class="message-log">
            @for (msg of svc.messages(); track msg.messageId) {
              <div class="msg-entry">
                <span class="msg-time">{{ formatTime(msg.timestamp) }}</span>
                <span class="msg-content">{{ msg.content }}</span>
              </div>
            }
          </div>
        </div>
      }

      <!-- Document cards -->
      <div class="doc-section">
        <h2>Documents</h2>
        <div class="doc-grid">
          @for (doc of documents(); track doc.document_id) {
            <div class="doc-card" [class]="'state-' + doc.state.toLowerCase().replace('_', '-')">
              <div class="doc-header">
                <span class="doc-id">{{ doc.document_id }}</span>
                <span class="doc-state-badge">{{ doc.state }}</span>
              </div>
              <div class="doc-body">
                <div class="doc-field">
                  <span class="label">Account</span>
                  <span class="value">{{ getAccountName(doc) }}</span>
                </div>
                <div class="doc-field">
                  <span class="label">Amount</span>
                  <span class="value">{{ doc.currency }} {{ getAmount(doc) | number:'1.2-2' }}</span>
                </div>
                <div class="doc-field">
                  <span class="label">Date</span>
                  <span class="value">{{ getPaymentDate(doc) }}</span>
                </div>
                @if (doc.review_reason) {
                  <div class="review-reason">⚠ {{ doc.review_reason }}</div>
                }
              </div>
            </div>
          }
        </div>
      </div>
    </div>
  `,
  styles: [`
    .pipeline-page { max-width: 1200px; }

    .page-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 2rem;
    }

    .controls {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    h1 {
      font-size: 1.5rem;
      font-weight: 700;
      margin: 0;
      color: #f0f0f5;
    }

    .subtitle {
      margin: 0.25rem 0 0;
      color: #6e6e8a;
      font-size: 0.875rem;
    }

    h2 {
      font-size: 1rem;
      font-weight: 600;
      margin: 0 0 1rem;
      color: #c0c0d0;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .btn {
      padding: 0.5rem 1.25rem;
      border: none;
      border-radius: 0.5rem;
      font-weight: 600;
      font-size: 0.875rem;
      cursor: pointer;
      transition: all 0.15s;
    }

    .btn-primary {
      background: #6c5ce7;
      color: #fff;
    }
    .btn-primary:hover { background: #5a4bd6; }

    .btn-danger {
      background: #e74c3c;
      color: #fff;
    }
    .btn-danger:hover { background: #c0392b; }

    /* Pipeline track */
    .pipeline-track {
      display: flex;
      align-items: center;
      background: #111118;
      border-radius: 0.75rem;
      padding: 1.5rem 2rem;
      margin-bottom: 2rem;
      border: 1px solid #1e1e2e;
    }

    .stage {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.5rem;
      flex-shrink: 0;
    }

    .stage-dot {
      width: 2.5rem;
      height: 2.5rem;
      border-radius: 50%;
      background: #1a1a28;
      border: 2px solid #2a2a3e;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1rem;
      color: #555570;
      transition: all 0.3s ease;
    }

    .stage.completed .stage-dot {
      background: #2d6b4f;
      border-color: #2ecc71;
      color: #2ecc71;
    }

    .stage.active .stage-dot {
      background: #2d2d6b;
      border-color: #6c5ce7;
      color: #a29bfe;
    }

    .pulse {
      animation: pulse 1.2s ease-in-out infinite;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.4; }
    }

    .stage-label {
      font-size: 0.7rem;
      color: #6e6e8a;
      text-align: center;
      white-space: nowrap;
    }

    .stage.completed .stage-label { color: #2ecc71; }
    .stage.active .stage-label { color: #a29bfe; }

    .stage-connector {
      flex: 1;
      height: 2px;
      background: #2a2a3e;
      margin: 0 0.5rem;
      margin-bottom: 1.5rem;
      transition: background 0.3s;
    }

    .stage-connector.completed { background: #2ecc71; }

    /* Live feed */
    .live-feed {
      background: #111118;
      border: 1px solid #1e1e2e;
      border-radius: 0.75rem;
      padding: 1.25rem;
      margin-bottom: 2rem;
      max-height: 300px;
      overflow-y: auto;
    }

    .live-dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      background: #e74c3c;
      border-radius: 50%;
      animation: pulse 1s ease-in-out infinite;
    }

    .message-log { display: flex; flex-direction: column; gap: 0.25rem; }

    .msg-entry {
      display: flex;
      gap: 0.75rem;
      font-size: 0.8rem;
      font-family: 'JetBrains Mono', 'Fira Code', monospace;
      line-height: 1.5;
    }

    .msg-time { color: #555570; white-space: nowrap; }
    .msg-content { color: #b0b0c8; }

    /* Document grid */
    .doc-section { margin-top: 1rem; }

    .doc-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 1rem;
    }

    .doc-card {
      background: #111118;
      border: 1px solid #1e1e2e;
      border-radius: 0.75rem;
      padding: 1rem;
      transition: border-color 0.2s;
    }

    .doc-card:hover { border-color: #3a3a5e; }

    .doc-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.75rem;
    }

    .doc-id {
      font-size: 0.8rem;
      font-weight: 600;
      color: #a0a0b8;
      font-family: monospace;
    }

    .doc-state-badge {
      font-size: 0.65rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 0.2rem 0.5rem;
      border-radius: 0.25rem;
      letter-spacing: 0.03em;
    }

    .state-finalized .doc-state-badge { background: #1a4731; color: #2ecc71; }
    .state-matched .doc-state-badge { background: #1a3147; color: #3498db; }
    .state-enriched .doc-state-badge { background: #2d2d47; color: #a29bfe; }
    .state-needs-review .doc-state-badge { background: #4a3520; color: #f39c12; }
    .state-human-review .doc-state-badge { background: #4a2020; color: #e74c3c; }
    .state-ingested .doc-state-badge { background: #2a2a3e; color: #8888a0; }
    .state-parsed .doc-state-badge { background: #2a3a3e; color: #1abc9c; }

    .doc-field {
      display: flex;
      justify-content: space-between;
      font-size: 0.8rem;
      padding: 0.25rem 0;
      border-bottom: 1px solid #1a1a28;
    }

    .doc-field .label { color: #6e6e8a; }
    .doc-field .value { color: #d0d0e0; font-weight: 500; }

    .review-reason {
      margin-top: 0.5rem;
      padding: 0.5rem;
      background: #1a1a10;
      border-radius: 0.375rem;
      font-size: 0.75rem;
      color: #f39c12;
      line-height: 1.4;
    }

    /* Support node track */
    .support-track {
      display: flex;
      justify-content: center;
      gap: 2rem;
      margin-bottom: 2rem;
      padding: 0.75rem 1rem;
    }

    .support-node {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.75rem;
      color: #6e6e8a;
    }

    .support-dot {
      color: #f39c12;
      font-size: 0.9rem;
    }

    .support-label {
      color: #8888a0;
    }

    /* Spreadsheet review panel */
    .review-panel {
      background: #111118;
      border: 2px solid #f39c12;
      border-radius: 0.75rem;
      padding: 1.5rem;
      margin-bottom: 2rem;
    }

    .review-header {
      display: flex;
      align-items: flex-start;
      gap: 0.75rem;
      margin-bottom: 1.25rem;
    }

    .review-icon { font-size: 1.5rem; }

    .review-header h2 {
      color: #f39c12;
      margin: 0;
    }

    .review-subtitle {
      color: #8888a0;
      font-size: 0.8rem;
      margin: 0.25rem 0 0;
    }

    .review-actions-row {
      display: flex;
      gap: 1rem;
      align-items: center;
      margin-bottom: 1.25rem;
      flex-wrap: wrap;
    }

    .btn-download {
      background: #1a3147;
      color: #3498db;
      text-decoration: none;
      padding: 0.5rem 1rem;
    }
    .btn-download:hover { background: #254a6b; }

    .upload-group {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .btn-upload {
      background: #2d2d47;
      color: #a29bfe;
      cursor: pointer;
      padding: 0.5rem 1rem;
    }
    .btn-upload:hover { background: #3a3a5e; }

    .upload-name {
      font-size: 0.75rem;
      color: #00b894;
    }

    .review-form {
      display: flex;
      gap: 1rem;
      margin-bottom: 1.25rem;
    }

    .review-form .form-group {
      flex: 1;
    }

    .review-form label {
      display: block;
      font-size: 0.75rem;
      font-weight: 600;
      color: #8888a0;
      margin-bottom: 0.375rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .review-form input[type="text"] {
      width: 100%;
      padding: 0.5rem 0.75rem;
      background: #0a0a0f;
      border: 1px solid #2a2a3e;
      border-radius: 0.5rem;
      color: #e0e0e6;
      font-size: 0.8rem;
      outline: none;
      box-sizing: border-box;
    }
    .review-form input[type="text"]:focus { border-color: #6c5ce7; }

    .review-buttons {
      display: flex;
      gap: 0.75rem;
    }

    .btn-approve {
      background: #1a3520;
      color: #2ecc71;
      border: 1px solid #2d4731;
    }
    .btn-approve:hover:not(:disabled) { background: #2d4731; }
    .btn-approve:disabled { opacity: 0.4; cursor: not-allowed; }

    .btn-reject {
      background: #2a1515;
      color: #e74c3c;
      border: 1px solid #4a2020;
    }
    .btn-reject:hover:not(:disabled) { background: #4a2020; }
    .btn-reject:disabled { opacity: 0.4; cursor: not-allowed; }

    /* Loading state */
    .pipeline-track.loading {
      justify-content: center;
      min-height: 80px;
    }

    .loading-text {
      color: #6e6e8a;
      font-size: 0.875rem;
      animation: pulse 1.2s ease-in-out infinite;
    }

    /* Spreadsheet exchange panel */
    .exchange-panel {
      background: #111118;
      border: 1px solid #1e1e2e;
      border-radius: 0.75rem;
      padding: 1.5rem;
      margin-bottom: 2rem;
    }

    .exchange-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 1.25rem;
    }

    .exchange-header h2 { margin: 0; }

    .exchange-badge {
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 0.25rem 0.6rem;
      border-radius: 0.25rem;
      letter-spacing: 0.04em;
    }

    .exchange-badge.paused {
      background: #4a3520;
      color: #f39c12;
    }

    .exchange-body {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }

    .exchange-card {
      display: flex;
      gap: 1rem;
      background: #0d0d14;
      border: 1px solid #1e1e2e;
      border-radius: 0.625rem;
      padding: 1.25rem;
    }

    .exchange-card-icon {
      font-size: 1.5rem;
      flex-shrink: 0;
      width: 2.5rem;
      height: 2.5rem;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #1a1a28;
      border-radius: 0.5rem;
    }

    .exchange-card-content {
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
    }

    .exchange-card-content h3 {
      font-size: 0.85rem;
      font-weight: 600;
      color: #d0d0e0;
      margin: 0;
    }

    .exchange-filename {
      font-family: 'JetBrains Mono', 'Fira Code', monospace;
      font-size: 0.75rem;
      color: #8888a0;
      margin: 0;
      word-break: break-all;
    }

    .exchange-panel.exchange-paused {
      border-color: #f39c12;
      border-width: 2px;
    }

    .exchange-badge.building {
      background: #2d2d47;
      color: #a29bfe;
    }

    .exchange-card.disabled {
      opacity: 0.5;
    }

    .review-section {
      margin-top: 1.25rem;
      padding-top: 1.25rem;
      border-top: 1px solid #1e1e2e;
    }
  `],
})
export class PipelineMonitorComponent implements OnInit {
  readonly svc = inject(AgUiEventService);
  private readonly http = inject(HttpClient);
  readonly pipelineNodes = signal<PipelineTopologyNode[]>([]);
  readonly supportNodes = signal<PipelineTopologyNode[]>([]);
  readonly topologyLoaded = signal(false);
  readonly documents = signal<PipelineDocument[]>([]);

  // Spreadsheet review state
  readonly uploadedFileName = signal('');
  private uploadedFilePath = '';
  reviewerId = '';
  reviewRationale = '';

  readonly latestSpreadsheet = signal<string | null>(null);

  constructor() {
    // Pick up spreadsheet filename from HITL interrupt
    effect(() => {
      const interrupt = this.svc.hitlInterrupt();
      if (!interrupt) return;
      const ctx = interrupt['context'] as Record<string, unknown> | undefined;
      const fullPath = (ctx?.['spreadsheet_path'] as string) ?? '';
      const name = fullPath.split('/').pop()?.split('\\').pop() ?? '';
      if (name) this.latestSpreadsheet.set(name);
    });

    // Re-fetch spreadsheet list when pipeline state changes (Build Spreadsheet completed)
    effect(() => {
      const state = this.svc.pipelineState();
      if (state?.completedSteps?.includes('Build Spreadsheet')) {
        this.loadSpreadsheets();
      }
    });
  }

  /** Show the exchange panel when Build Spreadsheet step is active or beyond */
  showExchangePanel(): boolean {
    // Always show if we already have a spreadsheet
    if (this.latestSpreadsheet()) return true;
    // Show if HITL interrupt is pending
    if (this.spreadsheetReviewPending()) return true;
    // Show if Build Spreadsheet step is active or completed
    const state = this.svc.pipelineState();
    if (!state) return false;
    const steps = state.completedSteps ?? [];
    const labels = this.pipelineNodes().map(n => n.label);
    const buildIdx = labels.indexOf('Build Spreadsheet');
    if (buildIdx < 0) return false;
    return steps.length >= buildIdx;
  }

  spreadsheetReviewPending(): boolean {
    const interrupt = this.svc.hitlInterrupt();
    if (!interrupt) return false;
    const ctx = interrupt['context'] as Record<string, unknown> | undefined;
    return !!ctx?.['spreadsheet_path'];
  }

  async ngOnInit(): Promise<void> {
    const [topology, docs] = await Promise.all([
      this.svc.loadTopology(),
      this.svc.loadDocuments(),
    ]);
    this.pipelineNodes.set(topology.nodes);
    this.supportNodes.set(topology.supportNodes);
    this.topologyLoaded.set(true);
    this.documents.set(docs);
    this.loadSpreadsheets();
  }

  private loadSpreadsheets(): void {
    this.http.get<{ filename: string }[]>('/api/spreadsheet/list').subscribe({
      next: (files) => {
        if (files.length > 0) {
          this.latestSpreadsheet.set(files[0].filename);
        }
      },
    });
  }

  spreadsheetFilename(): string {
    const interrupt = this.svc.hitlInterrupt();
    const ctx = interrupt?.['context'] as Record<string, unknown> | undefined;
    const fullPath = (ctx?.['spreadsheet_path'] as string) ?? '';
    return fullPath.split('/').pop()?.split('\\').pop() ?? '';
  }

  downloadSpreadsheet(filename: string): void {
    if (!filename) return;
    const url = `${environment.apiBaseUrl}/spreadsheet/download/${encodeURIComponent(filename)}`;
    this.http.get(url, { responseType: 'blob' }).subscribe({
      next: (blob) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
        URL.revokeObjectURL(a.href);
      },
      error: () => this.svc.error.set('Spreadsheet download failed'),
    });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file, file.name);

    this.http.post<{ path: string; filename: string }>('/api/spreadsheet/upload', formData).subscribe({
      next: (res) => {
        this.uploadedFileName.set(res.filename);
        this.uploadedFilePath = res.path;
      },
      error: () => this.uploadedFileName.set('Upload failed'),
    });
  }

  approveSpreadsheet(): void {
    const review: Record<string, unknown> = {
      action: this.uploadedFilePath ? 'upload' : 'approve',
      reviewer_id: this.reviewerId,
      rationale: this.reviewRationale,
    };
    if (this.uploadedFilePath) {
      review['uploaded_path'] = this.uploadedFilePath;
    }
    const threadId = this.svc.threadId() ?? '';
    this.svc.hitlInterrupt.set(null);
    this.svc.resumePipeline(threadId, review);
  }

  rejectSpreadsheet(): void {
    const review = {
      action: 'reject',
      reviewer_id: this.reviewerId,
      rationale: this.reviewRationale,
    };
    const threadId = this.svc.threadId() ?? '';
    this.svc.hitlInterrupt.set(null);
    this.svc.resumePipeline(threadId, review);
  }

  isCompleted(label: string): boolean {
    return this.svc.pipelineState()?.completedSteps?.includes(label) ?? false;
  }

  isActive(label: string): boolean {
    const state = this.svc.pipelineState();
    if (!state) return false;
    const labels = this.pipelineNodes().map(n => n.label);
    return state.currentStep !== undefined &&
      !state.completedSteps.includes(label) &&
      labels.indexOf(label) === state.completedSteps.length;
  }

  formatTime(ts: number): string {
    return new Date(ts * 1000).toLocaleTimeString();
  }

  getAccountName(doc: PipelineDocument): string {
    if (typeof doc.account_name === 'string') return doc.account_name;
    return doc.account_name?.value ?? '—';
  }

  getAmount(doc: PipelineDocument): number {
    if (typeof doc.amount === 'number') return doc.amount;
    return parseFloat(doc.amount?.value ?? '0');
  }

  getPaymentDate(doc: PipelineDocument): string {
    if (typeof doc.payment_date === 'string') return doc.payment_date;
    return doc.payment_date?.value ?? '—';
  }
}

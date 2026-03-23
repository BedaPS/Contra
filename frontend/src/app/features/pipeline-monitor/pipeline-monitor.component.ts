import { Component, inject, OnInit, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { AgUiEventService } from '../../core/services/ag-ui-event.service';
import { PipelineDocument } from '../../core/models/ag-ui.models';

@Component({
  selector: 'app-pipeline-monitor',
  standalone: true,
  imports: [DecimalPipe],
  template: `
    <div class="pipeline-page">
      <header class="page-header">
        <div>
          <h1>Pipeline Monitor</h1>
          <p class="subtitle">Real-time document flow through the five-state reconciliation pipeline</p>
        </div>
        <div class="controls">
          @if (svc.isRunning()) {
            <button class="btn btn-danger" (click)="svc.stopRun()">■ Stop</button>
          } @else {
            <button class="btn btn-primary" (click)="svc.startRun()">▶ Run Pipeline</button>
          }
        </div>
      </header>

      <!-- Pipeline visualization -->
      <div class="pipeline-track">
        @for (stage of stages; track stage) {
          <div class="stage" [class.completed]="isCompleted(stage)" [class.active]="isActive(stage)">
            <div class="stage-dot">
              @if (isCompleted(stage)) {
                <span>✓</span>
              } @else if (isActive(stage)) {
                <span class="pulse">●</span>
              } @else {
                <span>○</span>
              }
            </div>
            <div class="stage-label">{{ formatStage(stage) }}</div>
          </div>
          @if (!$last) {
            <div class="stage-connector" [class.completed]="isCompleted(stage)"></div>
          }
        }
      </div>

      <!-- Live event feed -->
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
    .state-pii-redacted .doc-state-badge { background: #2d2d47; color: #a29bfe; }
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
  `],
})
export class PipelineMonitorComponent implements OnInit {
  readonly svc = inject(AgUiEventService);
  readonly stages = ['Ingested', 'Parsed', 'PII_Redacted', 'Matched', 'Finalized'];
  readonly documents = signal<PipelineDocument[]>([]);

  async ngOnInit(): Promise<void> {
    const docs = await this.svc.loadDocuments();
    this.documents.set(docs);
  }

  isCompleted(stage: string): boolean {
    return this.svc.pipelineState()?.completedSteps?.includes(stage) ?? false;
  }

  isActive(stage: string): boolean {
    const state = this.svc.pipelineState();
    if (!state) return false;
    return state.currentStep !== undefined &&
      !state.completedSteps.includes(stage) &&
      this.stages.indexOf(stage) === state.completedSteps.length;
  }

  formatStage(stage: string): string {
    return stage.replace('_', ' ');
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

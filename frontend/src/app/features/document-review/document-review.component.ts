import { Component, effect, inject, OnInit, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { AgUiEventService } from '../../core/services/ag-ui-event.service';
import { PipelineDocument } from '../../core/models/ag-ui.models';

@Component({
  selector: 'app-document-review',
  standalone: true,
  imports: [DecimalPipe],
  template: `
    <div class="review-page">
      <header class="page-header">
        <div>
          <h1>Document Review</h1>
          <p class="subtitle">Human-in-the-loop: review flagged documents requiring manual intervention</p>
        </div>
        <div class="counter">
          <span class="count">{{ reviewDocs().length }}</span>
          <span class="count-label">items pending</span>
        </div>
      </header>

      @if (reviewDocs().length === 0) {
        <div class="empty-state">
          <div class="empty-icon">✓</div>
          <p>No documents pending review. All clear.</p>
        </div>
      }

      @for (doc of reviewDocs(); track doc.document_id) {
        <div class="review-card" [class]="'severity-' + getSeverity(doc)">
          <div class="card-left">
            <div class="severity-bar"></div>
          </div>
          <div class="card-content">
            <div class="card-header">
              <div class="card-title-row">
                <span class="doc-id">{{ doc.document_id }}</span>
                <span class="state-badge" [class]="'badge-' + doc.state.toLowerCase().replace('_', '-')">
                  {{ doc.state.replace('_', ' ') }}
                </span>
              </div>
              <span class="doc-date">{{ doc.created_at }}</span>
            </div>

            <div class="card-details">
              <div class="detail-row">
                <span class="detail-label">Account Name</span>
                <span class="detail-value">{{ getAccountName(doc) }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">Amount</span>
                <span class="detail-value amount">{{ doc.currency }} {{ getAmount(doc) | number:'1.2-2' }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">Payment Date</span>
                <span class="detail-value">{{ getPaymentDate(doc) }}</span>
              </div>
            </div>

            @if (doc.review_reason) {
              <div class="reason-box">
                <span class="reason-icon">⚠</span>
                <span>{{ doc.review_reason }}</span>
              </div>
            }

            <div class="card-actions">
              <button class="btn btn-approve" (click)="onApprove(doc)">✓ Approve</button>
              <button class="btn btn-reject" (click)="onReject(doc)">✗ Reject</button>
              <button class="btn btn-escalate" (click)="onEscalate(doc)">↑ Escalate</button>
            </div>
          </div>
        </div>
      }

      @if (resolvedDocs().length > 0) {
        <div class="resolved-section">
          <h2>Recently Resolved</h2>
          @for (doc of resolvedDocs(); track doc.document_id) {
            <div class="resolved-row">
              <span class="doc-id">{{ doc.document_id }}</span>
              <span class="resolved-account">{{ getAccountName(doc) }}</span>
              <span class="resolved-action">{{ getResolution(doc) }}</span>
            </div>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .review-page { max-width: 800px; }

    .page-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 2rem;
    }

    h1 { font-size: 1.5rem; font-weight: 700; margin: 0; color: #f0f0f5; }
    .subtitle { margin: 0.25rem 0 0; color: #6e6e8a; font-size: 0.875rem; }
    h2 { font-size: 1rem; font-weight: 600; margin: 1.5rem 0 1rem; color: #c0c0d0; }

    .counter {
      display: flex;
      flex-direction: column;
      align-items: center;
      background: #111118;
      border: 1px solid #1e1e2e;
      border-radius: 0.75rem;
      padding: 0.75rem 1.25rem;
    }

    .count { font-size: 1.5rem; font-weight: 700; color: #f39c12; }
    .count-label { font-size: 0.65rem; color: #6e6e8a; text-transform: uppercase; letter-spacing: 0.05em; }

    .empty-state {
      text-align: center;
      padding: 4rem 2rem;
      color: #2ecc71;
    }

    .empty-icon { font-size: 3rem; margin-bottom: 1rem; }
    .empty-state p { font-size: 0.9rem; color: #555570; }

    /* Review card */
    .review-card {
      display: flex;
      background: #111118;
      border: 1px solid #1e1e2e;
      border-radius: 0.75rem;
      margin-bottom: 1rem;
      overflow: hidden;
      transition: border-color 0.2s;
    }

    .review-card:hover { border-color: #3a3a5e; }

    .card-left { width: 4px; flex-shrink: 0; }

    .severity-high .severity-bar { background: #e74c3c; }
    .severity-medium .severity-bar { background: #f39c12; }
    .severity-low .severity-bar { background: #3498db; }

    .severity-bar { width: 100%; height: 100%; }

    .card-content { flex: 1; padding: 1.25rem; }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 1rem;
    }

    .card-title-row {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .doc-id {
      font-family: monospace;
      font-weight: 600;
      font-size: 0.9rem;
      color: #d0d0e0;
    }

    .state-badge {
      font-size: 0.65rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 0.2rem 0.5rem;
      border-radius: 0.25rem;
      letter-spacing: 0.03em;
    }

    .badge-needs-review { background: #4a3520; color: #f39c12; }
    .badge-human-review { background: #4a2020; color: #e74c3c; }

    .doc-date { font-size: 0.75rem; color: #555570; }

    .card-details { margin-bottom: 0.75rem; }

    .detail-row {
      display: flex;
      justify-content: space-between;
      padding: 0.375rem 0;
      border-bottom: 1px solid #1a1a28;
      font-size: 0.8rem;
    }

    .detail-label { color: #6e6e8a; }
    .detail-value { color: #d0d0e0; font-weight: 500; }
    .detail-value.amount { color: #a29bfe; font-family: monospace; }

    .reason-box {
      display: flex;
      align-items: flex-start;
      gap: 0.5rem;
      background: #1a1a10;
      border: 1px solid #3a3520;
      border-radius: 0.5rem;
      padding: 0.75rem;
      margin-bottom: 1rem;
      font-size: 0.8rem;
      color: #f39c12;
      line-height: 1.5;
    }

    .reason-icon { font-size: 1rem; flex-shrink: 0; }

    .card-actions {
      display: flex;
      gap: 0.5rem;
    }

    .btn {
      padding: 0.5rem 1rem;
      border: 1px solid transparent;
      border-radius: 0.5rem;
      font-weight: 600;
      font-size: 0.8rem;
      cursor: pointer;
      transition: all 0.15s;
    }

    .btn-approve {
      background: #1a3520;
      color: #2ecc71;
      border-color: #2d4731;
    }
    .btn-approve:hover { background: #2d4731; }

    .btn-reject {
      background: #2a1515;
      color: #e74c3c;
      border-color: #4a2020;
    }
    .btn-reject:hover { background: #4a2020; }

    .btn-escalate {
      background: #1a1a28;
      color: #8888a0;
      border-color: #2a2a3e;
    }
    .btn-escalate:hover { background: #2a2a3e; color: #c0c0d0; }

    /* Resolved section */
    .resolved-section {
      margin-top: 2rem;
      padding-top: 1rem;
      border-top: 1px solid #1e1e2e;
    }

    .resolved-row {
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 0.5rem 0.75rem;
      font-size: 0.8rem;
      border-bottom: 1px solid #1a1a28;
    }

    .resolved-account { color: #8888a0; flex: 1; }
    .resolved-action {
      font-size: 0.7rem;
      font-weight: 600;
      text-transform: uppercase;
      color: #2ecc71;
    }
  `],
})
export class DocumentReviewComponent implements OnInit {
  private readonly svc = inject(AgUiEventService);
  readonly allDocs = signal<PipelineDocument[]>([]);
  private readonly resolutions = signal<Map<string, string>>(new Map());

  readonly reviewDocs = signal<PipelineDocument[]>([]);
  readonly resolvedDocs = signal<PipelineDocument[]>([]);

  constructor() {
    // Update documents from pipeline state in real time
    effect(() => {
      const state = this.svc.pipelineState();
      if (state?.documents?.length) {
        this.allDocs.set(state.documents as PipelineDocument[]);
        this.updateFilteredDocs();
      }
    });
  }

  async ngOnInit(): Promise<void> {
    const docs = await this.svc.loadDocuments();
    if (docs.length > 0) {
      this.allDocs.set(docs);
      this.updateFilteredDocs();
    }
  }

  onApprove(doc: PipelineDocument): void {
    this.resolve(doc, 'approved');
  }

  onReject(doc: PipelineDocument): void {
    this.resolve(doc, 'rejected');
  }

  onEscalate(doc: PipelineDocument): void {
    this.resolve(doc, 'escalated');
  }

  getResolution(doc: PipelineDocument): string {
    return this.resolutions().get(doc.document_id) ?? '';
  }

  getSeverity(doc: PipelineDocument): string {
    if (doc.state === 'Human_Review') return 'high';
    if (doc.state === 'Needs_Review') return 'medium';
    return 'low';
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

  private resolve(doc: PipelineDocument, action: string): void {
    this.resolutions.update(map => {
      const copy = new Map(map);
      copy.set(doc.document_id, action);
      return copy;
    });
    this.updateFilteredDocs();
  }

  private updateFilteredDocs(): void {
    const resolved = this.resolutions();
    const all = this.allDocs();
    this.reviewDocs.set(
      all.filter(d =>
        (d.state === 'Needs_Review' || d.state === 'Human_Review') &&
        !resolved.has(d.document_id)
      )
    );
    this.resolvedDocs.set(
      all.filter(d => resolved.has(d.document_id))
    );
  }
}

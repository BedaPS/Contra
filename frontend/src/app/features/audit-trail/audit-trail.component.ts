import { Component, OnInit, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { inject } from '@angular/core';
import { AgUiEventService } from '../../core/services/ag-ui-event.service';
import { AuditEntry } from '../../core/models/ag-ui.models';

@Component({
  selector: 'app-audit-trail',
  standalone: true,
  imports: [DecimalPipe],
  template: `
    <div class="audit-page">
      <header class="page-header">
        <div>
          <h1>Audit Trail</h1>
          <p class="subtitle">Append-only reasoning log — every state transition with input/output hashes</p>
        </div>
        <div class="stats">
          <div class="stat">
            <span class="stat-value">{{ entries().length }}</span>
            <span class="stat-label">Entries</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ uniqueAgents().length }}</span>
            <span class="stat-label">Agents</span>
          </div>
        </div>
      </header>

      <!-- Filters -->
      <div class="filters">
        <button
          class="filter-btn"
          [class.active]="activeFilter() === 'all'"
          (click)="setFilter('all')"
        >All</button>
        @for (agent of uniqueAgents(); track agent) {
          <button
            class="filter-btn"
            [class.active]="activeFilter() === agent"
            (click)="setFilter(agent)"
          >{{ formatAgent(agent) }}</button>
        }
      </div>

      <!-- Audit entries -->
      <div class="entries">
        @for (entry of filteredEntries(); track $index) {
          <div class="entry" [class]="'decision-' + entry.decision.toLowerCase()">
            <div class="entry-header">
              <div class="entry-meta">
                <span class="agent-badge">{{ formatAgent(entry.agent) }}</span>
                <span class="decision-badge">{{ entry.decision }}</span>
                <span class="transition">{{ entry.state_from }} → {{ entry.state_to }}</span>
              </div>
              <span class="entry-time">{{ entry.timestamp }}</span>
            </div>

            <div class="entry-rationale">{{ entry.rationale }}</div>

            <div class="entry-details">
              <div class="hash-row">
                <span class="hash-label">In</span>
                <code class="hash-value">{{ entry.input_hash }}</code>
              </div>
              <div class="hash-row">
                <span class="hash-label">Out</span>
                <code class="hash-value">{{ entry.output_hash }}</code>
              </div>
              @if (hasConfidenceScores(entry)) {
                <div class="confidence-row">
                  <span class="conf-label">Confidence</span>
                  <div class="conf-scores">
                    @for (score of getConfidenceEntries(entry); track score[0]) {
                      <span class="conf-pill" [class.high]="score[1] >= 0.85" [class.low]="score[1] < 0.85">
                        {{ score[0] }}: {{ score[1] | number:'1.2-2' }}
                      </span>
                    }
                  </div>
                </div>
              }
            </div>
          </div>
        }
      </div>
    </div>
  `,
  styles: [`
    .audit-page { max-width: 900px; }

    .page-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 1.5rem;
    }

    h1 { font-size: 1.5rem; font-weight: 700; margin: 0; color: #f0f0f5; }
    .subtitle { margin: 0.25rem 0 0; color: #6e6e8a; font-size: 0.875rem; }

    .stats {
      display: flex;
      gap: 1rem;
    }

    .stat {
      display: flex;
      flex-direction: column;
      align-items: center;
      background: #111118;
      border: 1px solid #1e1e2e;
      border-radius: 0.75rem;
      padding: 0.5rem 1rem;
      min-width: 60px;
    }

    .stat-value { font-size: 1.25rem; font-weight: 700; color: #a29bfe; }
    .stat-label { font-size: 0.6rem; color: #6e6e8a; text-transform: uppercase; letter-spacing: 0.05em; }

    /* Filters */
    .filters {
      display: flex;
      gap: 0.5rem;
      margin-bottom: 1.5rem;
      flex-wrap: wrap;
    }

    .filter-btn {
      padding: 0.375rem 0.875rem;
      border: 1px solid #2a2a3e;
      border-radius: 2rem;
      background: #111118;
      color: #8888a0;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }

    .filter-btn:hover { border-color: #6c5ce7; color: #c0c0d0; }
    .filter-btn.active { background: #6c5ce7; color: #fff; border-color: #6c5ce7; }

    /* Entries */
    .entries { display: flex; flex-direction: column; gap: 0.75rem; }

    .entry {
      background: #111118;
      border: 1px solid #1e1e2e;
      border-radius: 0.75rem;
      padding: 1rem 1.25rem;
      border-left: 3px solid #2a2a3e;
    }

    .entry.decision-advance { border-left-color: #2ecc71; }
    .entry.decision-matched { border-left-color: #3498db; }
    .entry.decision-blocked { border-left-color: #f39c12; }
    .entry.decision-locked { border-left-color: #e74c3c; }

    .entry-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.5rem;
    }

    .entry-meta { display: flex; align-items: center; gap: 0.5rem; }

    .agent-badge {
      font-size: 0.7rem;
      font-weight: 700;
      padding: 0.15rem 0.5rem;
      border-radius: 0.25rem;
      background: #1a1a28;
      color: #a29bfe;
    }

    .decision-badge {
      font-size: 0.65rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 0.15rem 0.5rem;
      border-radius: 0.25rem;
    }

    .decision-advance .decision-badge { background: #1a3520; color: #2ecc71; }
    .decision-matched .decision-badge { background: #1a2535; color: #3498db; }
    .decision-blocked .decision-badge { background: #3a3015; color: #f39c12; }
    .decision-locked .decision-badge { background: #3a1515; color: #e74c3c; }

    .transition {
      font-size: 0.75rem;
      color: #6e6e8a;
      font-family: monospace;
    }

    .entry-time { font-size: 0.7rem; color: #555570; }

    .entry-rationale {
      font-size: 0.8rem;
      color: #b0b0c8;
      line-height: 1.5;
      margin-bottom: 0.75rem;
    }

    .entry-details {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
    }

    .hash-row {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.7rem;
    }

    .hash-label {
      color: #555570;
      font-weight: 600;
      width: 2rem;
      text-transform: uppercase;
      font-size: 0.6rem;
    }

    .hash-value {
      color: #6e6e8a;
      font-family: monospace;
      font-size: 0.7rem;
      background: #0d0d14;
      padding: 0.125rem 0.375rem;
      border-radius: 0.25rem;
    }

    .confidence-row {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-top: 0.375rem;
      flex-wrap: wrap;
    }

    .conf-label {
      color: #555570;
      font-weight: 600;
      font-size: 0.6rem;
      text-transform: uppercase;
      width: 4rem;
    }

    .conf-scores { display: flex; gap: 0.375rem; flex-wrap: wrap; }

    .conf-pill {
      font-size: 0.65rem;
      font-family: monospace;
      padding: 0.125rem 0.5rem;
      border-radius: 1rem;
      background: #1a1a28;
      color: #8888a0;
    }

    .conf-pill.high { color: #2ecc71; background: #1a2a20; }
    .conf-pill.low { color: #f39c12; background: #2a2510; }
  `],
})
export class AuditTrailComponent implements OnInit {
  private readonly svc = inject(AgUiEventService);
  readonly entries = signal<AuditEntry[]>([]);
  readonly activeFilter = signal<string>('all');

  readonly uniqueAgents = signal<string[]>([]);
  readonly filteredEntries = signal<AuditEntry[]>([]);

  async ngOnInit(): Promise<void> {
    const data = await this.svc.loadAuditEntries();
    this.entries.set(data);
    this.uniqueAgents.set([...new Set(data.map(e => e.agent))]);
    this.applyFilter();
  }

  setFilter(filter: string): void {
    this.activeFilter.set(filter);
    this.applyFilter();
  }

  formatAgent(agent: string): string {
    return agent
      .split('_')
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  }

  hasConfidenceScores(entry: AuditEntry): boolean {
    return Object.keys(entry.confidence_scores).length > 0;
  }

  getConfidenceEntries(entry: AuditEntry): [string, number][] {
    return Object.entries(entry.confidence_scores);
  }

  private applyFilter(): void {
    const filter = this.activeFilter();
    const all = this.entries();
    this.filteredEntries.set(
      filter === 'all' ? all : all.filter(e => e.agent === filter)
    );
  }
}

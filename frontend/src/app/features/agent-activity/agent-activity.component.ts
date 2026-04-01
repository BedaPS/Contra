import { Component, inject } from '@angular/core';
import { AgUiEventService } from '../../core/services/ag-ui-event.service';

@Component({
  selector: 'app-agent-activity',
  standalone: true,
  template: `
    <div class="activity-page">
      <header class="page-header">
        <div>
          <h1>Agent Activity</h1>
          <p class="subtitle">Live reasoning feed from pipeline agents — powered by AG-UI protocol</p>
        </div>
        <div class="controls">
          @if (svc.isRunning()) {
            <span class="live-indicator"><span class="live-dot"></span> Live</span>
            <button class="btn btn-danger" (click)="svc.stopRun()">■ Stop</button>
          } @else {
            <button class="btn btn-primary" (click)="svc.startRun()">▶ Start Run</button>
          }
        </div>
      </header>

      @if (svc.error()) {
        <div class="error-banner">{{ svc.error() }}</div>
      }

      <!-- Failures & Errors -->
      @if (svc.failures().length > 0) {
        <div class="failures-section">
          <h2>⚠ Failures &amp; Errors ({{ svc.failures().length }})</h2>
          @for (failure of svc.failures(); track $index) {
            <div class="failure-entry">
              <span class="failure-time">{{ formatEventTime(failure.timestamp) }}</span>
              @if (failure.stepName) {
                <span class="failure-step">{{ formatAgentName(failure.stepName) }}</span>
              }
              <span class="failure-msg">{{ failure.message }}</span>
            </div>
          }
        </div>
      }

      <!-- Step timeline -->
      <div class="steps-timeline">
        @for (step of svc.steps(); track step.stepId) {
          <div class="step-card" [class.running]="step.status === 'running'" [class.completed]="step.status === 'completed'">
            <div class="step-header">
              <div class="step-status-icon">
                @if (step.status === 'running') {
                  <span class="spinner"></span>
                } @else {
                  <span class="check">✓</span>
                }
              </div>
              <div class="step-info">
                <span class="step-name">{{ formatAgentName(step.stepName) }}</span>
                <span class="step-status">{{ step.status }}</span>
              </div>
            </div>

            <!-- Tool calls in this step -->
            @for (tc of step.toolCalls; track tc.toolCallId) {
              <div class="tool-call">
                <span class="tool-icon">⚙</span>
                <span class="tool-name">{{ tc.toolCallName }}</span>
                <span class="tool-status" [class.complete]="tc.status === 'completed'">
                  {{ tc.status === 'completed' ? '✓' : '...' }}
                </span>
                @if (tc.args) {
                  <div class="tool-args">{{ tc.args }}</div>
                }
              </div>
            }

            <!-- Messages in this step -->
            @for (msg of step.messages; track msg.messageId) {
              <div class="step-message">
                <div class="msg-text">{{ msg.content }}</div>
              </div>
            }

            @if (step.status === 'running') {
              <!-- Show in-progress messages -->
              @for (msg of svc.messages(); track msg.messageId) {
                <div class="step-message live">
                  <div class="msg-text">{{ msg.content }}<span class="cursor">▌</span></div>
                </div>
              }
            }
          </div>
        }

        @if (svc.steps().length === 0 && !svc.isRunning()) {
          <div class="empty-state">
            <div class="empty-icon">◉</div>
            <p>No agent activity yet. Start a pipeline run to see real-time agent reasoning.</p>
          </div>
        }
      </div>

      <!-- Event log -->
      @if (svc.events().length > 0) {
        <div class="event-log-section">
          <h2>Raw AG-UI Events ({{ svc.events().length }})</h2>
          <div class="event-log">
            @for (evt of svc.events().slice(-50); track $index) {
              <div class="event-entry" [class]="'event-' + evt['type'].toLowerCase().replace('_', '-')">
                <span class="event-type">{{ evt['type'] }}</span>
                <span class="event-time">{{ formatEventTime(evt.timestamp) }}</span>
              </div>
            }
          </div>
        </div>
      }
    </div>
  `,
  styles: [`
    .activity-page { max-width: 900px; }

    .page-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 2rem;
    }

    h1 { font-size: 1.5rem; font-weight: 700; margin: 0; color: #f0f0f5; }
    .subtitle { margin: 0.25rem 0 0; color: #6e6e8a; font-size: 0.875rem; }

    h2 { font-size: 1rem; font-weight: 600; margin: 0 0 1rem; color: #c0c0d0; }

    .controls { display: flex; align-items: center; gap: 0.75rem; }

    .btn {
      padding: 0.5rem 1.25rem;
      border: none;
      border-radius: 0.5rem;
      font-weight: 600;
      font-size: 0.875rem;
      cursor: pointer;
    }
    .btn-primary { background: #6c5ce7; color: #fff; }
    .btn-primary:hover { background: #5a4bd6; }
    .btn-danger { background: #e74c3c; color: #fff; }

    .live-indicator {
      display: flex;
      align-items: center;
      gap: 0.375rem;
      font-size: 0.75rem;
      font-weight: 600;
      color: #e74c3c;
      text-transform: uppercase;
    }

    .live-dot {
      width: 8px;
      height: 8px;
      background: #e74c3c;
      border-radius: 50%;
      animation: pulse 1s ease-in-out infinite;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }

    .error-banner {
      background: #2a1010;
      border: 1px solid #e74c3c;
      border-radius: 0.5rem;
      padding: 0.75rem 1rem;
      color: #e74c3c;
      font-size: 0.85rem;
      margin-bottom: 1.5rem;
    }

    .failures-section {
      background: #1a0f0f;
      border: 1px solid #4a2020;
      border-radius: 0.75rem;
      padding: 1.25rem;
      margin-bottom: 2rem;
    }

    .failures-section h2 {
      color: #e74c3c;
      font-size: 1rem;
      font-weight: 600;
      margin: 0 0 1rem;
    }

    .failure-entry {
      display: flex;
      align-items: flex-start;
      gap: 0.75rem;
      padding: 0.5rem 0;
      border-bottom: 1px solid #2a1515;
      font-size: 0.8rem;
    }

    .failure-time {
      color: #555570;
      white-space: nowrap;
      font-family: monospace;
      font-size: 0.7rem;
    }

    .failure-step {
      color: #e74c3c;
      font-weight: 600;
      white-space: nowrap;
    }

    .failure-msg {
      color: #e0a0a0;
      line-height: 1.4;
    }

    /* Step cards */
    .steps-timeline {
      display: flex;
      flex-direction: column;
      gap: 1rem;
      margin-bottom: 2rem;
    }

    .step-card {
      background: #111118;
      border: 1px solid #1e1e2e;
      border-radius: 0.75rem;
      padding: 1.25rem;
    }

    .step-card.running { border-color: #6c5ce7; }
    .step-card.completed { border-color: #2d4731; }

    .step-header {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 0.75rem;
    }

    .step-status-icon {
      width: 2rem;
      height: 2rem;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    .spinner {
      width: 1rem;
      height: 1rem;
      border: 2px solid #2a2a4e;
      border-top-color: #6c5ce7;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    @keyframes spin { to { transform: rotate(360deg); } }

    .check { color: #2ecc71; font-size: 1rem; }

    .step-info { display: flex; flex-direction: column; }

    .step-name {
      font-weight: 600;
      font-size: 0.9rem;
      color: #e0e0f0;
    }

    .step-status {
      font-size: 0.7rem;
      color: #6e6e8a;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    /* Tool calls */
    .tool-call {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 0.75rem;
      background: #0d0d14;
      border-radius: 0.375rem;
      margin-bottom: 0.5rem;
      font-size: 0.8rem;
      flex-wrap: wrap;
    }

    .tool-icon { color: #6c5ce7; }
    .tool-name { color: #a29bfe; font-family: monospace; font-weight: 600; }
    .tool-status { color: #6e6e8a; margin-left: auto; }
    .tool-status.complete { color: #2ecc71; }

    .tool-args {
      width: 100%;
      font-family: monospace;
      font-size: 0.7rem;
      color: #555570;
      padding-top: 0.25rem;
    }

    /* Messages */
    .step-message {
      padding: 0.5rem 0;
      border-top: 1px solid #1a1a28;
    }

    .step-message.live { border-top: none; }

    .msg-text {
      font-size: 0.8rem;
      color: #b0b0c8;
      line-height: 1.6;
    }

    .cursor {
      color: #6c5ce7;
      animation: blink 0.8s step-end infinite;
    }

    @keyframes blink {
      50% { opacity: 0; }
    }

    /* Empty state */
    .empty-state {
      text-align: center;
      padding: 4rem 2rem;
      color: #555570;
    }

    .empty-icon { font-size: 3rem; margin-bottom: 1rem; }
    .empty-state p { font-size: 0.9rem; }

    /* Event log */
    .event-log-section {
      background: #111118;
      border: 1px solid #1e1e2e;
      border-radius: 0.75rem;
      padding: 1.25rem;
      max-height: 250px;
      overflow-y: auto;
    }

    .event-log { display: flex; flex-direction: column; gap: 0.125rem; }

    .event-entry {
      display: flex;
      justify-content: space-between;
      font-family: monospace;
      font-size: 0.7rem;
      padding: 0.2rem 0.5rem;
      border-radius: 0.25rem;
    }

    .event-entry:hover { background: #1a1a28; }

    .event-type { color: #8888a0; }
    .event-time { color: #555570; }

    .event-run-started .event-type,
    .event-run-finished .event-type { color: #6c5ce7; }
    .event-step-started .event-type,
    .event-step-finished .event-type { color: #2ecc71; }
    .event-text-message-content .event-type { color: #3498db; }
    .event-tool-call-start .event-type { color: #f39c12; }
    .event-state-snapshot .event-type { color: #e74c3c; }
  `],
})
export class AgentActivityComponent {
  readonly svc = inject(AgUiEventService);

  formatAgentName(name: string): string {
    return name
      .split('_')
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  }

  formatEventTime(ts: number): string {
    return new Date(ts * 1000).toLocaleTimeString();
  }
}

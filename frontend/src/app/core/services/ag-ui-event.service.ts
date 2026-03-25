import { Injectable, signal, computed } from '@angular/core';
import { environment } from '../../../environments/environment';
import {
  AgUiEvent,
  PipelineState,
  AgentStep,
  AgentMessage,
  AgentToolCall,
  PipelineDocument,
  AuditEntry,
  PipelineTopology,
} from '../models/ag-ui.models';

/**
 * Service that consumes AG-UI protocol events from the backend SSE endpoint.
 * Manages pipeline state, agent steps, and message feeds using Angular signals.
 */
@Injectable({ providedIn: 'root' })
export class AgUiEventService {
  // ── Signals ──
  readonly isRunning = signal(false);
  readonly runId = signal<string | null>(null);
  readonly threadId = signal<string | null>(null);
  readonly events = signal<AgUiEvent[]>([]);
  readonly steps = signal<AgentStep[]>([]);
  readonly pipelineState = signal<PipelineState | null>(null);
  readonly messages = signal<AgentMessage[]>([]);
  readonly error = signal<string | null>(null);
  readonly hitlInterrupt = signal<Record<string, unknown> | null>(null);

  // ── Computed ──
  readonly currentStep = computed(() => {
    const s = this.steps();
    return s.find(step => step.status === 'running') ?? null;
  });

  readonly completedSteps = computed(() =>
    this.steps().filter(s => s.status === 'completed')
  );

  private eventSource: EventSource | null = null;
  private activeMessages = new Map<string, string>();
  private activeToolCalls = new Map<string, AgentToolCall>();

  /**
   * Start a new pipeline run by connecting to the backend SSE endpoint.
   */
  startRun(): void {
    this.reset();
    this.isRunning.set(true);
    this.error.set(null);

    const url = `${environment.apiBaseUrl}/agents/stream`;
    this.eventSource = new EventSource(url);

    this.eventSource.onmessage = (event: MessageEvent) => {
      const parsed: AgUiEvent = JSON.parse(event.data);
      this.events.update(prev => [...prev, parsed]);
      this.processEvent(parsed);
    };

    this.eventSource.onerror = () => {
      this.eventSource?.close();
      this.eventSource = null;
      this.isRunning.set(false);
    };
  }

  /**
   * Stop the current run and close the SSE connection.
   */
  stopRun(): void {
    this.eventSource?.close();
    this.eventSource = null;
    this.isRunning.set(false);
  }

  /**
   * Reset all state for a fresh run.
   */
  reset(): void {
    this.stopRun();
    this.runId.set(null);
    this.threadId.set(null);
    this.events.set([]);
    this.steps.set([]);
    this.pipelineState.set(null);
    this.messages.set([]);
    this.error.set(null);
    this.hitlInterrupt.set(null);
    this.activeMessages.clear();
    this.activeToolCalls.clear();
  }

  private processEvent(event: AgUiEvent): void {
    switch (event['type']) {
      case 'RUN_STARTED':
        this.runId.set(event['runId'] as string);
        this.threadId.set((event['threadId'] as string) ?? null);
        break;

      case 'STEP_STARTED':
        this.steps.update(prev => [
          ...prev,
          {
            stepName: event['stepName'] as string,
            stepId: event['stepId'] as string,
            status: 'running',
            messages: [],
            toolCalls: [],
          },
        ]);
        break;

      case 'STEP_FINISHED': {
        const stepId = event['stepId'] as string;
        this.steps.update(prev =>
          prev.map(s => s.stepId === stepId ? { ...s, status: 'completed' as const } : s)
        );
        break;
      }

      case 'TEXT_MESSAGE_START': {
        const msgId = event['messageId'] as string;
        this.activeMessages.set(msgId, '');
        break;
      }

      case 'TEXT_MESSAGE_CONTENT': {
        const msgId = event['messageId'] as string;
        const existing = this.activeMessages.get(msgId) ?? '';
        const newContent = existing + (event['content'] as string);
        this.activeMessages.set(msgId, newContent);

        // Update the messages signal with the latest content
        this.messages.update(prev => {
          const idx = prev.findIndex(m => m.messageId === msgId);
          const msg: AgentMessage = {
            messageId: msgId,
            role: 'assistant',
            content: newContent,
            timestamp: event['timestamp'] as number,
          };
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = msg;
            return updated;
          }
          return [...prev, msg];
        });
        break;
      }

      case 'TEXT_MESSAGE_END': {
        const msgId = event['messageId'] as string;
        // Add the final message to the current step
        const content = this.activeMessages.get(msgId) ?? '';
        this.steps.update(prev => {
          const running = prev.find(s => s.status === 'running');
          if (!running) return prev;
          return prev.map(s =>
            s.stepId === running.stepId
              ? {
                  ...s,
                  messages: [
                    ...s.messages,
                    { messageId: msgId, role: 'assistant', content, timestamp: event['timestamp'] as number },
                  ],
                }
              : s
          );
        });
        this.activeMessages.delete(msgId);
        break;
      }

      case 'TOOL_CALL_START': {
        const tc: AgentToolCall = {
          toolCallId: event['toolCallId'] as string,
          toolCallName: event['toolCallName'] as string,
          args: '',
          status: 'running',
        };
        this.activeToolCalls.set(tc.toolCallId, tc);
        break;
      }

      case 'TOOL_CALL_ARGS': {
        const tcId = event['toolCallId'] as string;
        const tc = this.activeToolCalls.get(tcId);
        if (tc) {
          tc.args += event['delta'] as string;
          this.activeToolCalls.set(tcId, { ...tc });
        }
        break;
      }

      case 'TOOL_CALL_END': {
        const tcId = event['toolCallId'] as string;
        const tc = this.activeToolCalls.get(tcId);
        if (tc) {
          tc.status = 'completed';
          // Add to current running step
          this.steps.update(prev => {
            const running = prev.find(s => s.status === 'running');
            if (!running) return prev;
            return prev.map(s =>
              s.stepId === running.stepId
                ? { ...s, toolCalls: [...s.toolCalls, { ...tc }] }
                : s
            );
          });
          this.activeToolCalls.delete(tcId);
        }
        break;
      }

      case 'STATE_SNAPSHOT': {
        const snapshot = event['snapshot'] as PipelineState;
        this.pipelineState.set(snapshot);
        break;
      }

      case 'HITL_INTERRUPT': {
        this.hitlInterrupt.set(event as Record<string, unknown>);
        break;
      }

      case 'RUN_FINISHED':
        this.isRunning.set(false);
        this.eventSource?.close();
        this.eventSource = null;
        break;

      case 'RUN_ERROR':
        this.error.set((event['message'] as string) ?? 'Pipeline run failed');
        this.isRunning.set(false);
        this.eventSource?.close();
        this.eventSource = null;
        break;
    }
  }

  // ── Static data loaders ──

  async loadDocuments(): Promise<PipelineDocument[]> {
    const res = await fetch(`${environment.apiBaseUrl}/documents`);
    return res.json();
  }

  async loadAuditEntries(): Promise<AuditEntry[]> {
    const res = await fetch(`${environment.apiBaseUrl}/audit/entries`);
    return res.json();
  }

  async loadTopology(): Promise<PipelineTopology> {
    const res = await fetch(`${environment.apiBaseUrl}/pipeline/topology`);
    return res.json();
  }

  /**
   * Resume a paused pipeline (HITL interrupt) by POSTing review data.
   * The backend streams resumed events back via SSE.
   */
  resumePipeline(threadId: string, review: Record<string, unknown>): void {
    this.isRunning.set(true);
    this.error.set(null);

    const url = `${environment.apiBaseUrl}/agents/resume?thread_id=${encodeURIComponent(threadId)}`;

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(review),
    }).then(async (response) => {
      if (!response.ok || !response.body) {
        this.error.set('Failed to resume pipeline');
        this.isRunning.set(false);
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const parsed: AgUiEvent = JSON.parse(line.slice(6));
            this.events.update(prev => [...prev, parsed]);
            this.processEvent(parsed);
          }
        }
      }
    }).catch(() => {
      this.error.set('Resume connection failed');
      this.isRunning.set(false);
    });
  }
}

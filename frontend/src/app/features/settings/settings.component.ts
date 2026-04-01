import { ChangeDetectorRef, Component, OnInit, signal, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

interface LLMSettingsResponse {
  provider: string;
  api_key_set: boolean;
  model: string;
  base_url: string;
  temperature: number;
  source_directory: string;
  work_directory: string;
  review_directory: string;
  output_directory: string;
}

interface LLMSettingsPayload {
  provider: string;
  api_key: string;
  model: string;
  base_url: string;
  temperature: number;
  source_directory: string;
  work_directory: string;
  review_directory: string;
  output_directory: string;
}

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="settings-page">
      <header class="page-header">
        <div>
          <h1>LLM Settings</h1>
          <p class="subtitle">Configure the language model provider for the reconciliation pipeline</p>
        </div>
      </header>

      <div class="settings-card">
        <div class="form-group">
          <label for="provider">Provider</label>
          <select id="provider" [(ngModel)]="provider" (ngModelChange)="onProviderChange()">
            @for (p of providers; track p.value) {
              <option [value]="p.value">{{ p.label }}</option>
            }
          </select>
          <span class="hint">{{ providerHint() }}</span>
        </div>

        @if (provider !== 'stub') {
          @if (provider !== 'local') {
            <div class="form-group">
              <label for="apiKey">API Key</label>
              <div class="key-input-row">
                <input
                  id="apiKey"
                  [type]="showKey ? 'text' : 'password'"
                  [(ngModel)]="apiKey"
                  placeholder="Enter API key"
                  autocomplete="off"
                />
                <button class="btn btn-icon" (click)="showKey = !showKey" type="button">
                  {{ showKey ? '◉' : '○' }}
                </button>
              </div>
              @if (apiKeySet() && !apiKey) {
                <span class="hint success">✓ API key is configured</span>
              }
            </div>
          }

          <div class="form-group">
            <label for="model">Model</label>
            <input id="model" type="text" [(ngModel)]="model" [placeholder]="modelPlaceholder()" />
            <span class="hint">{{ modelHint() }}</span>
          </div>

          @if (provider === 'local' || provider === 'openai') {
            <div class="form-group">
              <label for="baseUrl">Base URL</label>
              <input
                id="baseUrl"
                type="text"
                [(ngModel)]="baseUrl"
                [placeholder]="baseUrlPlaceholder()"
              />
              <span class="hint">
                @if (provider === 'local') {
                  Ollama default: http://localhost:11434/v1
                } @else {
                  Optional — leave empty for default OpenAI endpoint
                }
              </span>
            </div>
          }

          <div class="form-group">
            <label for="temperature">Temperature: {{ temperature }}</label>
            <input
              id="temperature"
              type="range"
              min="0"
              max="2"
              step="0.1"
              [(ngModel)]="temperature"
            />
            <div class="range-labels">
              <span>Precise (0)</span>
              <span>Creative (2)</span>
            </div>
          </div>
        }

        <div class="actions">
          <button class="btn btn-primary" (click)="save()" [disabled]="saving()">
            @if (saving()) {
              Saving…
            } @else {
              Save Settings
            }
          </button>
          @if (statusMessage()) {
            <span class="status" [class.error]="statusIsError()">{{ statusMessage() }}</span>
          }
        </div>
      </div>

      <div class="settings-card" style="margin-top: 2rem;">
        <h2 class="section-title">Directory Settings</h2>
        <p class="subtitle">Configure source and work directories for file ingestion</p>

        <div class="form-group">
          <label for="sourceDirectory">Source Directory</label>
          <input
            id="sourceDirectory"
            type="text"
            [(ngModel)]="sourceDirectory"
            placeholder="e.g. /data/incoming or C:\\Incoming"
          />
          <span class="hint">Directory where incoming payment proof files are placed</span>
        </div>

        <div class="form-group">
          <label for="workDirectory">Work Directory</label>
          <input
            id="workDirectory"
            type="text"
            [(ngModel)]="workDirectory"
            placeholder="e.g. /data/work or C:\\Work"
          />
          <span class="hint">Directory where files are copied for pipeline processing</span>
        </div>

        <div class="form-group">
          <label for="reviewDirectory">Review Directory</label>
          <input
            id="reviewDirectory"
            type="text"
            [(ngModel)]="reviewDirectory"
            placeholder="e.g. /data/review or C:\\Review"
          />
          <span class="hint">Shared directory where spreadsheets are placed for human review</span>
        </div>

        <div class="form-group">
          <label for="outputDirectory">Output Directory</label>
          <input
            id="outputDirectory"
            type="text"
            [(ngModel)]="outputDirectory"
            placeholder="e.g. /data/output or C:\\Output"
          />
          <span class="hint">Output directory where results.xlsx and accuracy.jsonl are written</span>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .settings-page { max-width: 640px; }

    .page-header {
      margin-bottom: 2rem;
    }
    .page-header h1 {
      font-size: 1.5rem;
      font-weight: 700;
      color: #e0e0e6;
      margin: 0 0 0.25rem;
    }
    .subtitle {
      color: #8888a0;
      font-size: 0.875rem;
      margin: 0;
    }

    .section-title {
      font-size: 1.25rem;
      font-weight: 700;
      color: #e0e0e6;
      margin: 0 0 0.25rem;
    }

    .settings-card {
      background: #111118;
      border: 1px solid #1e1e2e;
      border-radius: 12px;
      padding: 2rem;
    }

    .form-group {
      margin-bottom: 1.5rem;
    }
    .form-group label {
      display: block;
      font-size: 0.8125rem;
      font-weight: 600;
      color: #c0c0d0;
      margin-bottom: 0.5rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    select, input[type="text"], input[type="password"] {
      width: 100%;
      padding: 0.625rem 0.875rem;
      background: #0a0a0f;
      border: 1px solid #2a2a3e;
      border-radius: 8px;
      color: #e0e0e6;
      font-size: 0.875rem;
      font-family: inherit;
      outline: none;
      transition: border-color 0.15s;
      box-sizing: border-box;
    }
    select:focus, input[type="text"]:focus, input[type="password"]:focus {
      border-color: #6c5ce7;
    }
    select option {
      background: #111118;
      color: #e0e0e6;
    }

    input[type="range"] {
      width: 100%;
      accent-color: #6c5ce7;
    }

    .range-labels {
      display: flex;
      justify-content: space-between;
      font-size: 0.75rem;
      color: #555570;
      margin-top: 0.25rem;
    }

    .hint {
      display: block;
      font-size: 0.75rem;
      color: #555570;
      margin-top: 0.375rem;
    }
    .hint.success { color: #00b894; }

    .key-input-row {
      display: flex;
      gap: 0.5rem;
    }
    .key-input-row input { flex: 1; }

    .btn {
      padding: 0.625rem 1.25rem;
      border: none;
      border-radius: 8px;
      font-size: 0.875rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }
    .btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .btn-primary {
      background: #6c5ce7;
      color: #fff;
    }
    .btn-primary:hover:not(:disabled) {
      background: #5a4bd6;
    }
    .btn-icon {
      background: #1a1a28;
      color: #8888a0;
      border: 1px solid #2a2a3e;
      padding: 0.625rem 0.75rem;
      border-radius: 8px;
      cursor: pointer;
    }

    .actions {
      display: flex;
      align-items: center;
      gap: 1rem;
      margin-top: 2rem;
      padding-top: 1.5rem;
      border-top: 1px solid #1e1e2e;
    }

    .status {
      font-size: 0.8125rem;
      color: #00b894;
    }
    .status.error { color: #ff6b6b; }
  `]
})
export class SettingsComponent implements OnInit {
  private http = inject(HttpClient);
  private cdr = inject(ChangeDetectorRef);

  providers = [
    { value: 'gemini', label: 'Google Gemini' },
    { value: 'openai', label: 'OpenAI' },
    { value: 'anthropic', label: 'Anthropic' },
    { value: 'local', label: 'Local (Ollama / vLLM)' },
    { value: 'stub', label: 'Stub (development)' },
  ];

  provider = 'stub';
  apiKey = '';
  model = '';
  baseUrl = '';
  temperature = 0;
  showKey = false;
  sourceDirectory = '';
  workDirectory = '';
  reviewDirectory = '';
  outputDirectory = '';

  apiKeySet = signal(false);
  saving = signal(false);
  statusMessage = signal('');
  statusIsError = signal(false);

  ngOnInit(): void {
    this.loadSettings();
  }

  onProviderChange(): void {
    if (!this.model || this.isDefaultModel(this.model)) {
      this.model = this.defaultModelFor(this.provider);
    }
  }

  providerHint(): string {
    const hints: Record<string, string> = {
      gemini: 'Uses Google AI Studio / Vertex AI',
      openai: 'GPT models via OpenAI API',
      anthropic: 'Claude models via Anthropic API',
      local: 'Any OpenAI-compatible local server',
      stub: 'Returns canned responses — no API key needed',
    };
    return hints[this.provider] ?? '';
  }

  modelPlaceholder(): string {
    return this.defaultModelFor(this.provider);
  }

  modelHint(): string {
    const hints: Record<string, string> = {
      gemini: 'e.g. gemini-2.0-flash, gemini-2.5-pro',
      openai: 'e.g. gpt-4o, gpt-4o-mini',
      anthropic: 'e.g. claude-sonnet-4-20250514, claude-3-haiku-20240307',
      local: 'e.g. llama3, mistral, codellama',
    };
    return hints[this.provider] ?? '';
  }

  baseUrlPlaceholder(): string {
    return this.provider === 'local' ? 'http://localhost:11434/v1' : 'https://api.openai.com/v1';
  }

  save(): void {
    this.saving.set(true);
    this.statusMessage.set('');

    const payload: LLMSettingsPayload = {
      provider: this.provider,
      api_key: this.apiKey,
      model: this.model || this.defaultModelFor(this.provider),
      base_url: this.baseUrl,
      temperature: this.temperature,
      source_directory: this.sourceDirectory,
      work_directory: this.workDirectory,
      review_directory: this.reviewDirectory,
      output_directory: this.outputDirectory,
    };

    this.http.put<LLMSettingsResponse>('/api/settings/llm', payload).subscribe({
      next: (res) => {
        this.applyResponse(res);
        this.saving.set(false);
        this.statusMessage.set('Settings saved successfully');
        this.statusIsError.set(false);
      },
      error: (err) => {
        this.saving.set(false);
        this.statusMessage.set(err?.error?.detail ?? 'Failed to save settings');
        this.statusIsError.set(true);
      },
    });
  }

  private loadSettings(): void {
    this.http.get<LLMSettingsResponse>('/api/settings/llm').subscribe({
      next: (res) => {
        this.applyResponse(res);
        this.cdr.markForCheck();
      },
      error: () => { /* defaults are fine */ },
    });
  }

  private applyResponse(res: LLMSettingsResponse): void {
    this.provider = res.provider;
    this.apiKeySet.set(res.api_key_set);
    this.model = res.model;
    this.baseUrl = res.base_url;
    this.temperature = res.temperature;
    this.sourceDirectory = res.source_directory;
    this.workDirectory = res.work_directory;
    this.reviewDirectory = res.review_directory;
    this.outputDirectory = res.output_directory;
    if (!this.apiKey && res.api_key_set) {
      this.apiKey = '';
    }
  }

  private defaultModelFor(provider: string): string {
    const defaults: Record<string, string> = {
      gemini: 'gemini-2.0-flash',
      openai: 'gpt-4o',
      anthropic: 'claude-sonnet-4-20250514',
      local: 'llama3',
      stub: 'stub',
    };
    return defaults[provider] ?? '';
  }

  private isDefaultModel(model: string): boolean {
    return Object.values({
      gemini: 'gemini-2.0-flash',
      openai: 'gpt-4o',
      anthropic: 'claude-sonnet-4-20250514',
      local: 'llama3',
      stub: 'stub',
    } as Record<string, string>).includes(model);
  }
}
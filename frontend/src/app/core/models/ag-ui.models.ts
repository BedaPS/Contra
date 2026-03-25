/**
 * AG-UI Protocol event types used by the Contra pipeline.
 * Maps to the AG-UI EventType enum from @ag-ui/core.
 */

export interface AgUiEvent {
  type: string;
  timestamp: number;
  [key: string]: unknown;
}

export interface PipelineState {
  documents: PipelineDocument[];
  currentStep: string;
  pipeline: string[];
  completedSteps: string[];
  ocrConfidence?: Record<string, number>;
  matchResult?: MatchResult;
}

export interface PipelineDocument {
  document_id: string;
  source_email: string;
  account_name: { value: string; confidence_score: number } | string;
  amount: { value: string; confidence_score: number } | number;
  currency: { value: string; confidence_score: number } | string;
  bank_reference_id?: { value: string; confidence_score: number } | null;
  payment_date: { value: string; confidence_score: number } | string;
  attachment_mime_type?: string;
  state: string;
  created_at?: string;
  review_reason?: string;
}

export interface MatchResult {
  match_id: string;
  document_id: string;
  bank_transaction_id: string;
  decision: string;
  amount_delta: number;
  bank_reference_id_match: boolean;
  temporal_delta_days: number;
  rationale: string;
}

export interface AuditEntry {
  agent: string;
  timestamp: string;
  input_hash: string;
  output_hash: string;
  state_from: string;
  state_to: string;
  decision: string;
  rationale: string;
  confidence_scores: Record<string, number>;
}

export interface PipelineTopologyNode {
  id: string;
  label: string;
}

export interface PipelineTopologyEdge {
  source: string;
  target: string;
  condition?: string;
}

export interface PipelineTopology {
  nodes: PipelineTopologyNode[];
  supportNodes: PipelineTopologyNode[];
  edges: PipelineTopologyEdge[];
}

export interface AgentStep {
  stepName: string;
  stepId: string;
  status: 'running' | 'completed';
  messages: AgentMessage[];
  toolCalls: AgentToolCall[];
}

export interface AgentMessage {
  messageId: string;
  role: string;
  content: string;
  timestamp: number;
}

export interface AgentToolCall {
  toolCallId: string;
  toolCallName: string;
  args: string;
  status: 'running' | 'completed';
}

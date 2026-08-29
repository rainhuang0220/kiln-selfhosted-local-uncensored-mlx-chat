export type Role = "system" | "user" | "assistant" | "tool";

export type MessageStatus =
  | "pending"
  | "streaming"
  | "complete"
  | "interrupted"
  | "error";

export interface TokenUsage {
  input: number;
  output: number;
  total: number;
  cached?: number;
  source?: string;
  tokensPerSecond?: number;
}

export interface GenerationParams {
  temperature: number;
  topP: number;
  topK: number;
  maxTokens: number;
  enableThinking: boolean;
  reasoningEffort: "low" | "medium" | "xhigh";
}

export interface Occupancy {
  effective_window_tokens: number;
  model_max_tokens: number;
  prompt_tokens: number;
  completion_budget: number;
  reserved_output_tokens: number;
  ratio: number;
  document_pack?: {
    applied: boolean;
    original_tokens: number;
    kept_tokens: number;
    chunks_total: number;
    chunks_kept: number;
  } | null;
}

export interface SentMessage {
  role: Role;
  content: string;
  reasoning_content?: string;
}

export interface ContextSnapshot {
  request_id?: string;
  conversation_id: string;
  model: string;
  params: Record<string, unknown>;
  effective_system_prompt: string;
  sent_messages: SentMessage[];
  occupancy: Occupancy;
  truncation: {
    applied: boolean;
    policy: string;
    dropped_message_ids: string[];
  };
  history_summary?: string | null;
  compressed?: boolean;
}

export interface Message {
  id: string;
  role: Exclude<Role, "system"> | "system";
  content: string;
  reasoning?: string | null;
  status: MessageStatus;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  finish_reason?: string | null;
  error?: string | null;
  created_at?: number;
  snapshot?: ContextSnapshot;
  usage?: TokenUsage;
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  model: string;
  created_at: number;
  updated_at: number;
  message_count: number;
  last_message_preview: string | null;
  total_tokens: number;
}

export interface Health {
  status: string;
  provider: { name: string; reachable: boolean; base_url: string };
  model: string;
  context_window: number;
  practical_prompt_budget: number;
  default_max_tokens: number;
  max_tokens_cap?: number;
  enable_thinking: boolean;
}

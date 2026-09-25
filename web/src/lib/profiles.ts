import type { GenerationParams, GenerationProfile } from "../types/chat";

export const PROFILE_PRESETS: Record<GenerationProfile, GenerationParams> = {
  interactive_dialogue: {
    profile: "interactive_dialogue",
    temperature: 0.7,
    topP: 0.8,
    topK: 20,
    minP: 0,
    presencePenalty: 0.5,
    presenceContextSize: 256,
    frequencyPenalty: 0,
    frequencyContextSize: 256,
    repetitionPenalty: 1.0,
    repetitionContextSize: 128,
    maxTokens: 1536,
    enableThinking: false,
    reasoningEffort: "medium",
  },
  balanced: {
    profile: "balanced",
    temperature: 0.7,
    topP: 0.9,
    topK: 20,
    minP: 0,
    presencePenalty: 0,
    presenceContextSize: 256,
    frequencyPenalty: 0,
    frequencyContextSize: 256,
    repetitionPenalty: 1.0,
    repetitionContextSize: 128,
    maxTokens: 4096,
    enableThinking: false,
    reasoningEffort: "medium",
  },
  reasoning: {
    profile: "reasoning",
    temperature: 0.6,
    topP: 0.95,
    topK: 20,
    minP: 0,
    presencePenalty: 0,
    presenceContextSize: 20,
    frequencyPenalty: 0,
    frequencyContextSize: 20,
    repetitionPenalty: 1.0,
    repetitionContextSize: 20,
    maxTokens: 8192,
    enableThinking: true,
    reasoningEffort: "medium",
  },
  long_form: {
    profile: "long_form",
    temperature: 0.7,
    topP: 0.9,
    topK: 20,
    minP: 0,
    presencePenalty: 0.3,
    presenceContextSize: 256,
    frequencyPenalty: 0,
    frequencyContextSize: 256,
    repetitionPenalty: 1.0,
    repetitionContextSize: 128,
    maxTokens: 2048,
    enableThinking: false,
    reasoningEffort: "medium",
  },
};

export const PROFILE_LABELS: Record<GenerationProfile, string> = {
  interactive_dialogue: "Interactive Dialogue",
  balanced: "Balanced",
  reasoning: "Reasoning",
  long_form: "Long Form (20K+)",
};

export function isIncompleteTerminal(finish?: string | null, terminal?: string | null): boolean {
  const state = terminal || finish || "";
  return [
    "interrupted_transport",
    "interrupted_user",
    "upstream_protocol_error",
    "timeout",
    "generation_error",
    "repetition_guard",
    "unknown_terminal",
    "completed_with_transport_error",
    "error",
    "abort",
  ].includes(state);
}

export function terminalCopy(finish?: string | null, terminal?: string | null): string | null {
  const state = terminal || finish || "";
  if (state === "length" || state === "completed_length") return "已达到输出上限";
  if (state === "repetition_guard") return "检测到明显重复，已停止生成";
  if (state === "timeout") return "生成超时";
  if (state === "interrupted_user" || state === "abort") return "已中断";
  if (state === "completed_with_transport_error") return "传输有损坏，这段回复可能缺字";
  if (
    state === "interrupted_transport" ||
    state === "upstream_protocol_error" ||
    state === "unknown_terminal" ||
    state === "generation_error"
  ) {
    return "生成未正常完成";
  }
  return null;
}

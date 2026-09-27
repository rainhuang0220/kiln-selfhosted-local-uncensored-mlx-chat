import type { GenerationParams, GenerationProfile } from "../types/chat";

const INTERACTIVE_PARAMS: GenerationParams = {
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
  maxTokens: 3072,
  enableThinking: false,
  reasoningEffort: "medium",
};

export const PROFILE_PRESETS: Record<GenerationProfile, GenerationParams> = {
  immersive: {
    profile: "immersive",
    temperature: 0.78,
    topP: 0.9,
    topK: 40,
    minP: 0.05,
    presencePenalty: 0.25,
    presenceContextSize: 1024,
    frequencyPenalty: 0,
    frequencyContextSize: 256,
    repetitionPenalty: 1.0,
    repetitionContextSize: 256,
    maxTokens: 6144,
    enableThinking: false,
    reasoningEffort: "low",
  },
  interactive_dialogue: { ...INTERACTIVE_PARAMS },
  /** Alias of interactive_dialogue for API / older clients. */
  fast: { ...INTERACTIVE_PARAMS, profile: "fast" },
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
    temperature: 0.78,
    topP: 0.9,
    topK: 40,
    minP: 0.05,
    presencePenalty: 0.25,
    presenceContextSize: 1024,
    frequencyPenalty: 0,
    frequencyContextSize: 256,
    repetitionPenalty: 1.0,
    repetitionContextSize: 256,
    maxTokens: 6144,
    enableThinking: false,
    reasoningEffort: "low",
  },
};

/** Profiles shown in the main dropdown (Balanced / Reasoning / Long Form stay in presets only). */
export const PROFILE_PRIMARY: GenerationProfile[] = ["immersive", "interactive_dialogue"];

export const PROFILE_LABELS: Record<GenerationProfile, string> = {
  immersive: "沉浸对话",
  interactive_dialogue: "短对话",
  fast: "短对话",
  balanced: "Balanced",
  reasoning: "Reasoning",
  long_form: "Long Form",
};

export const PROFILE_HELP: Partial<Record<GenerationProfile, string>> = {
  immersive:
    "默认。短指令也会把场景写开，并记住你钉过的事实。 / Default. Short cues still advance the scene and keep pinned facts.",
  interactive_dialogue: "短回复，更快。不会自动续写。 / Short replies, faster. No auto-continue.",
  fast: "短回复，更快。不会自动续写。 / Short replies, faster. No auto-continue.",
};

export const DRAFT_MAX_CHARS = 5000;

export function normalizePrimaryProfile(profile: GenerationProfile): GenerationProfile {
  if (profile === "fast") return "interactive_dialogue";
  if (PROFILE_PRIMARY.includes(profile)) return profile;
  if (profile === "long_form") return "immersive";
  return PROFILE_PRIMARY[0];
}

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

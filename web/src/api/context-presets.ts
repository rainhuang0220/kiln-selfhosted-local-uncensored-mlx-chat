import { apiFetch } from "./http";
import type {
  ContextPresetPayload,
  ContextPresetPreview,
  ContextPresetRecord,
  MeSlots,
  PresetExtractMeta,
  PresetTimelineEvent,
  SimpleCharacter,
} from "../types/context-preset";

export const MODEL_DID_NOT_ANALYZE = "模型没有分析，请重试。没有使用规则名册。";

type UnknownObject = Record<string, unknown>;

function object(value: unknown): UnknownObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownObject : {};
}

function string(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function meSlots(raw: unknown): MeSlots {
  const value = object(raw);
  return {
    identity: string(value.identity) || "暂无",
    real_background: string(value.real_background) || "暂无",
    explicit_prefs: string(value.explicit_prefs) || "暂无",
  };
}

function character(raw: unknown): SimpleCharacter {
  const entry = object(raw);
  const event = string(entry.one_event);
  return {
    id: string(entry.id) || undefined,
    name: string(entry.name),
    identity: string(entry.identity) || string(entry.role) || string(entry.description) || "人物",
    one_event: event || undefined,
  };
}

function timelineEvent(raw: unknown, index: number): PresetTimelineEvent {
  const entry = object(raw);
  const who = Array.isArray(entry.who)
    ? entry.who.filter((name): name is string => typeof name === "string" && name.trim().length > 0)
    : [];
  return {
    id: string(entry.id) || "manual-" + index,
    order: index + 1,
    who,
    summary: string(entry.summary),
    when: string(entry.when) || "未注明",
    chronology: "source_order",
    scope: entry.scope === "active" ? "active" : "reference",
    evidence: string(entry.evidence),
  };
}

export function normalizePresetPayload(raw: unknown): ContextPresetPayload {
  const value = object(raw);
  // Migrate any leftover legacy blobs so the SPA never crashes.
  if (!("current_scene" in value) && ("active_scene" in value || "active_character" in value)) {
    const actor = object(value.active_character);
    const legacyChars = Array.isArray(value.characters) ? value.characters.map(character) : [];
    if (string(actor.name)) {
      legacyChars.unshift({
        name: string(actor.name),
        identity: string(actor.description) || "人物",
      });
    }
    return {
      current_scene: string(value.active_scene),
      me: {
        identity: string(value.user_persona) || "暂无",
        real_background: Array.isArray(value.background_facts)
          ? (value.background_facts as string[]).filter(Boolean).join("；") || "暂无"
          : "暂无",
        explicit_prefs: Array.isArray(value.preferences)
          ? (value.preferences as string[]).filter(Boolean).join("；") || "暂无"
          : "暂无",
      },
      characters: legacyChars,
      timeline: [],
      active_character_ids: [],
    };
  }
  return {
    current_scene: string(value.current_scene),
    me: meSlots(value.me),
    me_identity_helper: string(value.me_identity_helper) || undefined,
    characters: Array.isArray(value.characters) ? value.characters.map(character) : [],
    // Public binder rows only — drop empty who and never surface IR homework fields.
    timeline: (Array.isArray(value.timeline) ? value.timeline : [])
      .map(timelineEvent)
      .filter((event) => event.who.length > 0),
    active_character_ids: Array.isArray(value.active_character_ids)
      ? value.active_character_ids.filter((item): item is string => typeof item === "string")
      : [],
  };
}

export function emptyPresetPayload(): ContextPresetPayload {
  return {
    current_scene: "",
    me: { identity: "暂无", real_background: "暂无", explicit_prefs: "暂无" },
    characters: [],
    timeline: [],
    active_character_ids: [],
  };
}

async function jsonOrError(response: Response): Promise<unknown> {
  const raw = await response.text();
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    data = null;
  }
  if (!response.ok) {
    const error = object(object(data).error);
    const detail = object(data).detail;
    throw new Error(string(error.message) || string(detail) || raw || `HTTP ${response.status}`);
  }
  return data;
}

function record(raw: unknown): ContextPresetRecord {
  const value = object(raw);
  if (!string(value.id)) throw new Error("预设响应缺少 ID");
  return {
    id: string(value.id),
    title: string(value.title),
    payload: normalizePresetPayload(value.payload),
    updated_at: typeof value.updated_at === "number" || typeof value.updated_at === "string" ? value.updated_at : 0,
    source_text: string(value.source_text),
    owner_id: string(value.owner_id) || undefined,
  };
}

function extractMeta(raw: unknown): PresetExtractMeta | null {
  const value = object(raw);
  if (!string(value.mode)) return null;
  return {
    mode: string(value.mode),
    model_ran: value.model_ran === true,
    elapsed_s: typeof value.elapsed_s === "number" ? value.elapsed_s : undefined,
    window_chars: Array.isArray(value.window_chars)
      ? value.window_chars.filter((n): n is number => typeof n === "number")
      : undefined,
    reason: string(value.reason) || undefined,
  };
}

export async function previewContextPreset(text: string): Promise<ContextPresetPreview> {
  // 「解析并预览」 only: long pastes need the 9B people extract (server cap 90s); no rules roster.
  const response = await apiFetch("/context/presets/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, deep: true }),
  });
  if (response.status === 502 || response.status === 503 || response.status === 504) {
    throw new Error(`${MODEL_DID_NOT_ANALYZE}（HTTP ${response.status}）`);
  }
  const result = object(await jsonOrError(response));
  const draft = object(result.draft);
  return { payload: normalizePresetPayload(draft.payload || draft), extract: extractMeta(draft.extract) };
}

export async function listContextPresets(): Promise<ContextPresetRecord[]> {
  const response = await apiFetch("/context/presets");
  const result = object(await jsonOrError(response));
  return Array.isArray(result.data) ? result.data.map(record) : [];
}

export async function getContextPreset(id: string): Promise<ContextPresetRecord> {
  const response = await apiFetch(`/context/presets/${encodeURIComponent(id)}`);
  return record(await jsonOrError(response));
}

export async function saveContextPreset(
  input: { title: string; payload: ContextPresetPayload; source_text: string; conversation_id?: string },
  id?: string,
): Promise<ContextPresetRecord> {
  const response = await apiFetch(id ? `/context/presets/${encodeURIComponent(id)}` : "/context/presets", {
    method: id ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return record(await jsonOrError(response));
}

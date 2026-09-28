import { apiFetch } from "./http";
import type { ContextPresetPayload, ContextPresetRecord, MeSlots, SimpleCharacter } from "../types/context-preset";

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
      active_character_ids: [],
    };
  }
  return {
    current_scene: string(value.current_scene),
    me: meSlots(value.me),
    characters: Array.isArray(value.characters) ? value.characters.map(character) : [],
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

export async function previewContextPreset(text: string): Promise<ContextPresetPayload> {
  // 「解析并预览」 only: rules harvest + optional 9B JSON enrich (server timeout ~20s).
  const response = await apiFetch("/context/presets/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, deep: true }),
  });
  const result = object(await jsonOrError(response));
  const draft = object(result.draft);
  return normalizePresetPayload(draft.payload || draft);
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

import { apiFetch } from "./http";
import type { ContextPresetPayload, ContextPresetRecord } from "../types/context-preset";

type UnknownObject = Record<string, unknown>;

function object(value: unknown): UnknownObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownObject : {};
}

function string(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function normalizePresetPayload(raw: unknown): ContextPresetPayload {
  const value = object(raw);
  const character = object(value.active_character);
  const references = object(value.references);
  return {
    active_scene: string(value.active_scene),
    user_persona: string(value.user_persona),
    background_facts: strings(value.background_facts),
    preferences: strings(value.preferences),
    active_character: {
      name: string(character.name),
      description: string(character.description),
      personality: string(character.personality),
      scenario: string(character.scenario),
      speech_style: string(character.speech_style),
      taboos: string(character.taboos),
      relationship_to_user: string(character.relationship_to_user),
      immutable_json: strings(character.immutable_json),
    },
    characters: Array.isArray(value.characters) ? value.characters.map((item) => {
      const entry = object(item);
      return {
        name: string(entry.name),
        role: string(entry.role),
        scope: entry.scope === "active" ? "active" as const : "reference" as const,
        notes: string(entry.notes),
      };
    }) : [],
    references: {
      people: Array.isArray(references.people) ? references.people.map((item) => {
        const entry = object(item);
        return { name: string(entry.name), role_hint: string(entry.role_hint) };
      }) : [],
      events: Array.isArray(references.events) ? references.events.map((item) => {
        const entry = object(item);
        return { label: string(entry.label), who: Array.isArray(entry.who) ? strings(entry.who).join("、") : string(entry.who), gist: string(entry.gist) };
      }) : [],
      register: strings(references.register),
      techniques: strings(references.techniques),
    },
    uncertain: strings(value.uncertain),
  };
}

export function emptyPresetPayload(): ContextPresetPayload {
  return normalizePresetPayload({});
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
  };
}

export async function previewContextPreset(text: string, options: { deep?: boolean } = {}): Promise<ContextPresetPayload> {
  const response = await apiFetch("/context/presets/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options.deep ? { text, deep: true } : { text }),
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
  input: { title: string; payload: ContextPresetPayload; source_text: string },
  id?: string,
): Promise<ContextPresetRecord> {
  const response = await apiFetch(id ? `/context/presets/${encodeURIComponent(id)}` : "/context/presets", {
    method: id ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return record(await jsonOrError(response));
}

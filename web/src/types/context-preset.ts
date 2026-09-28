export interface SimpleCharacter {
  id?: string;
  name: string;
  identity: string;
  one_event?: string;
}

export interface MeSlots {
  identity: string;
  real_background: string;
  explicit_prefs: string;
}

export interface PresetTimelineEvent {
  id: string;
  order: number;
  who: string[];
  suggested_who: string[];
  summary: string;
  when: string;
  chronology: "source_order";
  scope: "active" | "reference";
  evidence: string;
  source_span: { start: number; end: number } | null;
  needs_review: boolean;
}

export type ContextSegmentType =
  | "ROLE_DEFINITION" | "USER_AVATAR" | "USER_BACKGROUND" | "USER_PREFERENCE"
  | "CURRENT_SCENE" | "ENTITY_DEFINITION" | "ENTITY_ATTRIBUTE" | "WORLD_EVENT"
  | "DOCUMENT_META" | "UNKNOWN";

export interface ContextSegment {
  id: string;
  text: string;
  type: ContextSegmentType;
  scope: "live" | "reference";
  importance: number;
  source_span: { start: number; end: number };
  needs_review: boolean;
}

export interface ContextIR {
  version: 2;
  source_sha256: string;
  segments: ContextSegment[];
  persona: { role: string; rules: string[] };
  user_avatar: { identity: string; real_background: string };
  current_scene: string;
  entities: Record<string, unknown>[];
  relations: Record<string, unknown>[];
  events: Record<string, unknown>[];
  preferences: { id: string; category: string; content: string; do_not_literalize: boolean; source_span: { start: number; end: number } | null }[];
  conflicts: { kind: string; evidence: string; source_span: { start: number; end: number }; resolution: string }[];
  preference_field_at_compile?: string;
}

export interface ContextPresetPayload {
  current_scene: string;
  me: MeSlots;
  characters: SimpleCharacter[];
  timeline: PresetTimelineEvent[];
  context_ir?: ContextIR;
  /** Account character ids bound into this conversation (ids only). */
  active_character_ids?: string[];
}

export interface ContextPresetRecord {
  id: string;
  title: string;
  payload: ContextPresetPayload;
  updated_at: number | string;
  source_text?: string;
  owner_id?: string;
}

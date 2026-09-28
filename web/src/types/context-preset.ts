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

export interface ContextPresetPayload {
  current_scene: string;
  me: MeSlots;
  characters: SimpleCharacter[];
  timeline: PresetTimelineEvent[];
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

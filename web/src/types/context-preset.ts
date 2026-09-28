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

/** Public Studio event row — binder already attached who[]; no IR homework fields. */
export interface PresetTimelineEvent {
  id: string;
  order: number;
  who: string[];
  summary: string;
  when: string;
  chronology: "source_order";
  scope: "active" | "reference";
  evidence: string;
}

export interface ContextPresetPayload {
  current_scene: string;
  me: MeSlots;
  me_identity_helper?: string;
  characters: SimpleCharacter[];
  timeline: PresetTimelineEvent[];
  /** Account character ids bound into this conversation (ids only). */
  active_character_ids?: string[];
}

/** Whether the local 9B analyzed a 解析并预览 request (preview only; never saved). */
export interface PresetExtractMeta {
  mode: string;
  model_ran: boolean;
  elapsed_s?: number;
  window_chars?: number[];
  reason?: string;
}

export interface ContextPresetPreview {
  payload: ContextPresetPayload;
  extract: PresetExtractMeta | null;
}

export interface ContextPresetRecord {
  id: string;
  title: string;
  payload: ContextPresetPayload;
  updated_at: number | string;
  source_text?: string;
  owner_id?: string;
}

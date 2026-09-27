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

export interface ContextPresetPayload {
  current_scene: string;
  me: MeSlots;
  characters: SimpleCharacter[];
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

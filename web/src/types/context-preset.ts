export interface PresetCharacter {
  name: string;
  role: string;
  scope: "active" | "reference";
  notes: string;
}

export interface ContextPresetPayload {
  active_scene: string;
  user_persona: string;
  background_facts: string[];
  preferences: string[];
  active_character: {
    name: string;
    description: string;
    personality: string;
    scenario: string;
    speech_style: string;
    taboos: string;
    relationship_to_user: string;
    immutable_json: string[];
  };
  characters: PresetCharacter[];
  references: {
    people: { name: string; role_hint: string }[];
    events: { label: string; who: string; gist: string }[];
    register: string[];
    techniques: string[];
  };
  uncertain: string[];
}

export interface ContextPresetRecord {
  id: string;
  title: string;
  payload: ContextPresetPayload;
  updated_at: number | string;
  source_text?: string;
}

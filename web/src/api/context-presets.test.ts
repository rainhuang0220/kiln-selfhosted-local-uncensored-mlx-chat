import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "./http";
import {
  getContextPreset,
  listContextPresets,
  normalizePresetPayload,
  previewContextPreset,
  saveContextPreset,
} from "./context-presets";

vi.mock("./http", () => ({ apiFetch: vi.fn() }));
const mocked = vi.mocked(apiFetch);

const payload = {
  active_scene: "茶室",
  user_persona: "来访者",
  background_facts: ["住在城南"],
  preferences: ["喜欢简短对话"],
  active_character: {
    name: "阿青", description: "茶师", personality: "沉稳", scenario: "接待客人",
    speech_style: "简短", taboos: "", relationship_to_user: "初识", immutable_json: ["不离开茶室"],
  },
  characters: [{ name: "阿青", role: "茶师", scope: "active" as const, notes: "主角" }],
  references: {
    people: [{ name: "小宋", role_hint: "仅供参考" }],
    events: [{ label: "旧事", who: "小宋", gist: "发生在过去" }],
    register: ["克制"], techniques: ["对话为主"],
  },
  uncertain: ["地点待定"],
};

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

describe("context preset API", () => {
  beforeEach(() => mocked.mockReset());

  it("previews the full source text and retains character scopes", async () => {
    mocked.mockResolvedValue(json({ draft: payload }));
    const longText = "场景" + "参考".repeat(1600) + "回到场景";
    const draft = await previewContextPreset(longText);
    expect(draft.characters[0].scope).toBe("active");
    expect(draft.references.people[0].name).toBe("小宋");
    expect(draft.background_facts).toEqual(["住在城南"]);
    expect(draft.preferences).toEqual(["喜欢简短对话"]);
    expect(mocked).toHaveBeenCalledWith("/context/presets/preview", expect.objectContaining({
      method: "POST", body: JSON.stringify({ text: longText }),
    }));
  });

  it("requests optional local-model analysis only when selected", async () => {
    mocked.mockResolvedValue(json({ draft: payload }));
    await previewContextPreset("现实设定和参考材料", { deep: true });
    expect(mocked).toHaveBeenCalledWith("/context/presets/preview", expect.objectContaining({
      body: JSON.stringify({ text: "现实设定和参考材料", deep: true }),
    }));
  });

  it("fills missing optional collections so a partial draft stays editable", () => {
    const draft = normalizePresetPayload({ active_scene: "小店", active_character: { name: "店员" } });
    expect(draft.active_scene).toBe("小店");
    expect(draft.active_character.name).toBe("店员");
    expect(draft.active_character.immutable_json).toEqual([]);
    expect(draft.characters).toEqual([]);
    expect(draft.background_facts).toEqual([]);
    expect(draft.preferences).toEqual([]);
    expect(draft.references).toEqual({ people: [], events: [], register: [], techniques: [] });
  });

  it("keeps event participants when the preview returns a name array", () => {
    const draft = normalizePresetPayload({
      references: { events: [{ label: "旧事", who: ["小宋", "阿青"], gist: "发生在过去" }] },
    });
    expect(draft.references.events[0].who).toBe("小宋、阿青");
  });

  it("uses the routed list, detail, create, and update endpoints", async () => {
    const record = { id: "p-1", title: "茶室", payload, updated_at: 123 };
    mocked.mockResolvedValueOnce(json({ object: "list", data: [record] }))
      .mockResolvedValueOnce(json(record))
      .mockResolvedValueOnce(json(record))
      .mockResolvedValueOnce(json(record));
    expect((await listContextPresets())[0].id).toBe("p-1");
    expect((await getContextPreset("p-1")).title).toBe("茶室");
    await saveContextPreset({ title: "茶室", payload, source_text: "原文" });
    await saveContextPreset({ title: "茶室", payload, source_text: "原文" }, "p-1");
    expect(mocked.mock.calls.map(([url, init]) => [url, init?.method || "GET"])).toEqual([
      ["/context/presets", "GET"],
      ["/context/presets/p-1", "GET"],
      ["/context/presets", "POST"],
      ["/context/presets/p-1", "PATCH"],
    ]);
  });
});

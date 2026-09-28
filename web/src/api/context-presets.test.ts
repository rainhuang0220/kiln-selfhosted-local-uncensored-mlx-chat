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
  current_scene: "茶室",
  me: {
    identity: "来访者",
    real_background: "住在城南",
    explicit_prefs: "喜欢简短对话",
  },
  characters: [
    { id: "c1", name: "阿青", identity: "茶师", one_event: "初识" },
    { name: "小宋", identity: "旧识" },
  ],
  timeline: [{
    id: "ev-1", order: 1, who: ["小宋"], suggested_who: [], summary: "小宋递来一把伞",
    when: "那天", chronology: "source_order" as const, scope: "reference" as const,
    evidence: "那天小宋递来一把伞。", source_span: { start: 10, end: 22 }, needs_review: false,
  }],
  active_character_ids: ["c1"],
};

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

describe("context preset API", () => {
  beforeEach(() => mocked.mockReset());

  it("previews the full source text into simple scene/me/character rows", async () => {
    mocked.mockResolvedValue(json({ draft: payload }));
    const longText = "场景" + "参考".repeat(1600) + "回到场景";
    const draft = await previewContextPreset(longText);
    expect(draft.current_scene).toBe("茶室");
    expect(draft.me.real_background).toBe("住在城南");
    expect(draft.characters[0].name).toBe("阿青");
    expect(draft.characters[0].identity).toBe("茶师");
    expect(draft.timeline[0].who).toEqual(["小宋"]);
    expect(draft.timeline[0].evidence).toBe("那天小宋递来一把伞。");
    expect(mocked).toHaveBeenCalledWith("/context/presets/preview", expect.objectContaining({
      method: "POST", body: JSON.stringify({ text: longText, deep: true }),
    }));
  });

  it("sends deep enrich on 解析并预览 only (chat send stays rules-only)", async () => {
    mocked.mockResolvedValue(json({ draft: payload }));
    await previewContextPreset("现实设定和参考材料");
    expect(mocked).toHaveBeenCalledWith("/context/presets/preview", expect.objectContaining({
      body: JSON.stringify({ text: "现实设定和参考材料", deep: true }),
    }));
    expect(String(mocked.mock.calls[0][1]?.body)).toContain("\"deep\":true");
  });

  it("fills missing optional collections so a partial draft stays editable", () => {
    const draft = normalizePresetPayload({ current_scene: "小店", characters: [{ name: "店员", identity: "店员" }] });
    expect(draft.current_scene).toBe("小店");
    expect(draft.characters[0].name).toBe("店员");
    expect(draft.me.identity).toBe("暂无");
    expect(draft.me.real_background).toBe("暂无");
    expect(draft.me.explicit_prefs).toBe("暂无");
    expect(draft.timeline).toEqual([]);
  });

  it("migrates legacy preview blobs into the simple shape", () => {
    const draft = normalizePresetPayload({
      active_scene: "旧茶室",
      user_persona: "客人",
      background_facts: ["城南"],
      preferences: ["短句"],
      active_character: { name: "阿青", description: "茶师" },
      characters: [{ name: "小宋", role: "旧友", scope: "reference", notes: "往事" }],
    });
    expect(draft.current_scene).toBe("旧茶室");
    expect(draft.me.identity).toBe("客人");
    expect(draft.me.real_background).toBe("城南");
    expect(draft.characters.some((c) => c.name === "阿青")).toBe(true);
    expect(draft.characters.some((c) => c.name === "小宋" && c.identity === "旧友")).toBe(true);
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

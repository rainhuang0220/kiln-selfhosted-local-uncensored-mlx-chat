import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ContextPresetStudio, PresetEditor } from "./ContextPresetStudio";
import type { ContextPresetPayload } from "../types/context-preset";

const payload: ContextPresetPayload = {
  active_scene: "茶室会面",
  user_persona: "顾客",
  background_facts: ["住在城南"],
  preferences: ["喜欢简短对话"],
  active_character: {
    name: "阿青", description: "茶师", personality: "沉稳", scenario: "接待顾客",
    speech_style: "简短", taboos: "", relationship_to_user: "初识", immutable_json: ["保持角色"],
  },
  characters: [
    { name: "阿青", role: "茶师", scope: "active", notes: "当前" },
    { name: "小宋", role: "旧识", scope: "reference", notes: "仅作参考" },
  ],
  references: {
    people: [{ name: "小宋", role_hint: "旧识" }],
    events: [{ label: "往事", who: "小宋", gist: "过去发生" }],
    register: ["克制"], techniques: ["先对话"],
  },
  uncertain: ["日期不明"],
};

describe("context preset workspace", () => {
  it("keeps the current scene separate from reference material and exposes scope editing", () => {
    const html = renderToStaticMarkup(<PresetEditor payload={payload} onChange={vi.fn()} />);
    expect(html).toContain("当前场景");
    expect(html).toContain("用户身份");
    expect(html).toContain("当前扮演人物");
    expect(html).toContain("已确认的现实背景");
    expect(html).toContain("明确偏好");
    expect(html).toContain("住在城南");
    expect(html).toContain("参考人物与素材");
    expect(html).toContain("茶室会面");
    expect(html).toContain("小宋");
    expect(html).toContain('<option value="active" selected="">当前人物</option>');
    expect(html).toContain('<option value="reference" selected="">参考人物</option>');
  });

  it("offers both long-text analysis and manual structured editing before saving", () => {
    const html = renderToStaticMarkup(<ContextPresetStudio onClose={vi.fn()} onStartNewChat={vi.fn()} />);
    expect(html).toContain("粘贴长文本");
    expect(html).toContain("解析并预览");
    expect(html).toContain("直接编辑结构化信息");
    expect(html).toContain("保存预设");
    expect(html).toContain("仅在新会话开始时生效");
  });
});

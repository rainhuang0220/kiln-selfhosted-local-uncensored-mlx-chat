import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ContextPresetStudio, PresetEditor } from "./ContextPresetStudio";
import type { ContextPresetPayload } from "../types/context-preset";

const payload: ContextPresetPayload = {
  current_scene: "风俗店包间",
  me: {
    identity: "顾客",
    real_background: "住在城南",
    explicit_prefs: "喜欢简短对话",
  },
  characters: [
    { id: "c1", name: "阿青", identity: "茶师", one_event: "初识" },
    { id: "c2", name: "小宋", identity: "旧识", one_event: undefined },
  ],
  active_character_ids: ["c1"],
};

describe("context preset workspace", () => {
  it("shows simple scene / me / character rows without rejected panels", () => {
    const html = renderToStaticMarkup(<PresetEditor payload={payload} onChange={vi.fn()} />);
    expect(html).toContain("当前场景");
    expect(html).toContain("用户身份");
    expect(html).toContain("现实背景");
    expect(html).toContain("明确偏好");
    expect(html).toContain("人物");
    expect(html).toContain("阿青");
    expect(html).toContain("小宋");
    expect(html).not.toContain("当前对话锚点");
    expect(html).not.toContain("参考人物与素材");
    expect(html).not.toContain("深度分析");
  });

  it("offers one paste box and 解析并预览 without deep-analysis chrome", () => {
    const html = renderToStaticMarkup(<ContextPresetStudio onClose={vi.fn()} onStartNewChat={vi.fn()} />);
    expect(html).toContain("解析并预览");
    expect(html).not.toContain("当前对话锚点");
    expect(html).not.toContain("参考人物与素材");
    expect(html).not.toContain("深度分析");
    expect(html).not.toContain("直接编辑结构化信息");
  });
});

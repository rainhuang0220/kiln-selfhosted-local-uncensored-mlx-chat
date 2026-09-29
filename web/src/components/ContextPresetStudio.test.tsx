import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ContextPresetStudio, PresetEditor, RelatedEvents, eventsForPerson, previewStatus } from "./ContextPresetStudio";
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
  timeline: [{
    id: "ev-1", order: 1, who: ["小宋"], summary: "小宋递来一把伞",
    when: "那天", chronology: "source_order", scope: "reference",
    evidence: "那天小宋递来一把伞。",
  }],
  active_character_ids: ["c1"],
};

describe("context preset workspace", () => {
  it("shows scene / me / characters / bound events without IR homework", () => {
    const html = renderToStaticMarkup(<PresetEditor payload={payload} onChange={vi.fn()} />);
    expect(html).toContain("当前场景");
    expect(html).toContain("用户身份");
    expect(html).toContain("现实背景");
    expect(html).toContain("明确偏好");
    expect(html).toContain("人物");
    expect(html).toContain("阿青");
    expect(html).toContain("小宋");
    expect(html).toContain("已绑定事件");
    expect(html).toContain("小宋 · 小宋递来一把伞");
    expect(html).not.toContain("文档分区");
    expect(html).not.toContain("待确认");
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

  it("says the 9B ran and how long, or fails visibly instead of showing a rules roster", () => {
    expect(previewStatus({ mode: "model", model_ran: true, elapsed_s: 52.6, window_chars: [1363, 1397] }))
      .toEqual({ line: "模型已分析 · 53s", failed: false });
    expect(previewStatus({ mode: "model_failed", model_ran: false }))
      .toEqual({ line: "模型没有分析，请重试。没有使用规则名册。", failed: true });
    expect(previewStatus({ mode: "busy", model_ran: false }).failed).toBe(true);
    expect(previewStatus({ mode: "blocked", model_ran: false }).line).toBe("模型没有分析，请重试。没有使用规则名册。");
    expect(previewStatus({ mode: "rules_short", model_ran: false }).failed).toBe(false);
  });
});

const LONG = ("陆遥把薄册子翻到右上角写着日期的那一页，请人自己看，再慢慢合上。").repeat(20);

const bound: ContextPresetPayload = {
  current_scene: "接待室",
  me: { identity: "顾客", real_background: "", explicit_prefs: "" },
  characters: [
    { id: "p1", name: "陆遥", identity: "陆闻的姐姐", one_event: "旧的一件事残留" },
    { id: "p2", name: "唐宁", identity: "排球馆的成年队友" },
    { id: "p3", name: "许澄", identity: "技师" },
  ],
  timeline: [
    { id: "e1", order: 1, who: ["陆遥"], summary: "陆遥每天放学先去书店", when: "小学三年级", chronology: "source_order", scope: "reference", evidence: "" },
    { id: "e2", order: 2, who: ["唐宁", "陆遥"], summary: LONG.slice(0, 400), when: "那年夏天", chronology: "source_order", scope: "reference", evidence: "" },
    { id: "e3", order: 3, who: ["唐宁"], summary: "唐宁让我把球抛高一点", when: "高一", chronology: "source_order", scope: "reference", evidence: "" },
  ],
};

function peopleSection(html: string): string {
  return html.slice(html.indexOf('id="preset-people-title"'), html.indexOf('id="preset-timeline-title"'));
}

function findButton(node: unknown): { props: { onClick: () => void } } | null {
  if (!node || typeof node !== "object") return null;
  const element = node as { type?: unknown; props?: { children?: unknown; onClick?: () => void } };
  if (element.type === "button") return element as { props: { onClick: () => void } };
  const children = element.props?.children;
  for (const child of Array.isArray(children) ? children : [children]) {
    const hit = findButton(child);
    if (hit) return hit;
  }
  return null;
}

describe("character card related events", () => {
  it("S1 lists each person's bound events by exact who name, in timeline order", () => {
    expect(eventsForPerson("陆遥", bound.timeline).map((event) => event.id)).toEqual(["e1", "e2"]);
    expect(eventsForPerson("唐宁", bound.timeline).map((event) => event.id)).toEqual(["e2", "e3"]);
    expect(eventsForPerson("陆", bound.timeline)).toEqual([]);
    expect(eventsForPerson("", bound.timeline)).toEqual([]);
    const shuffled = [bound.timeline[1], bound.timeline[0]];
    expect(eventsForPerson("陆遥", shuffled).map((event) => event.id)).toEqual(["e1", "e2"]);

    const luyao = renderToStaticMarkup(<RelatedEvents events={eventsForPerson("陆遥", bound.timeline)} open onToggle={vi.fn()} />);
    expect(luyao).toContain("陆遥每天放学先去书店");
    expect(luyao).toContain(LONG.slice(0, 400));
    expect(luyao).not.toContain("唐宁让我把球抛高一点");
    const tangning = renderToStaticMarkup(<RelatedEvents events={eventsForPerson("唐宁", bound.timeline)} open onToggle={vi.fn()} />);
    expect(tangning).toContain("唐宁让我把球抛高一点");
    expect(tangning).not.toContain("陆遥每天放学先去书店");
  });

  it("S1 shows the full event as a wrapping block, capped at 500 characters", () => {
    const html = renderToStaticMarkup(<RelatedEvents events={[{ ...bound.timeline[1], summary: LONG }]} open onToggle={vi.fn()} />);
    expect(html).toContain('<p class="preset-related-text">');
    expect(html).toContain("那年夏天");
    expect(html).toContain(LONG.slice(0, 500));
    expect(html).not.toContain(LONG.slice(0, 501));
    expect(html).not.toContain("<input");
  });

  it("S2 character row has name and one-line identity, no 一件事 field", () => {
    const html = peopleSection(renderToStaticMarkup(<PresetEditor payload={bound} onChange={vi.fn()} />));
    expect(html).toContain("名称");
    expect(html).toContain("身份");
    expect(html).toContain('value="陆闻的姐姐"');
    expect(html).not.toContain("一件事");
    expect(html).not.toContain("旧的一件事残留");
    expect(html).not.toContain('placeholder="可空"');
    expect(html.match(/<input/g)?.length).toBe(bound.characters.length * 2);
  });

  it("S3 related events start collapsed with a count, and the header toggles them", () => {
    const html = renderToStaticMarkup(<PresetEditor payload={bound} onChange={vi.fn()} />);
    const people = peopleSection(html);
    expect(people.match(/class="preset-related-head"/g)?.length).toBe(3);
    expect(people).toContain('aria-expanded="false"');
    expect(people).not.toContain('aria-expanded="true"');
    expect(people).not.toContain("陆遥每天放学先去书店");
    expect(people).not.toContain("唐宁让我把球抛高一点");
    expect(people).toMatch(/相关事件<\/span><span class="preset-related-count">0</);

    const onToggle = vi.fn();
    const events = eventsForPerson("陆遥", bound.timeline);
    findButton(RelatedEvents({ events, open: false, onToggle }))?.props.onClick();
    expect(onToggle).toHaveBeenCalledTimes(1);
    const opened = renderToStaticMarkup(<RelatedEvents events={events} open onToggle={onToggle} />);
    expect(opened).toContain('aria-expanded="true"');
    expect(opened).toContain("陆遥每天放学先去书店");

    const empty = renderToStaticMarkup(<RelatedEvents events={[]} open onToggle={vi.fn()} />);
    expect(empty).toContain('preset-related-count">0<');
    expect(empty).not.toContain("<li");
  });

  it("keeps the bottom bound-event list, 当前场景 and 用户身份", () => {
    const html = renderToStaticMarkup(<PresetEditor payload={bound} onChange={vi.fn()} />);
    expect(html).toContain("当前场景");
    expect(html).toContain("用户身份");
    expect(html).toContain("已绑定事件");
    expect(html).toContain("添加事件");
    expect(html).toContain("唐宁 · 唐宁让我把球抛高一点");
  });
});

"""Render the narrative and one coherent event description per character."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "test"
SOURCE = DOCS / "多人物交织场景_输入.md"
GOLD = DOCS / "多人物交织场景_标准结构.json"
OUTPUT = DOCS / "scene" / "index.html"

def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def render() -> Path:
    source = SOURCE.read_text("utf-8")
    gold = json.loads(GOLD.read_text("utf-8"))
    people = gold["people"]
    for item in people:
        assert all(span in source for span in item["evidence"])

    paragraphs = [part.strip() for part in source.split("\n\n") if part.strip()]
    story = "\n".join(
        f'<p class="{"story-present" if i == len(paragraphs) - 1 else ""}">{esc(part)}</p>'
        for i, part in enumerate(paragraphs)
    )
    jump = "\n".join(
        f'<a href="#person-{i}">{esc(item["name"])}</a>' for i, item in enumerate(people)
    )
    people_html: list[str] = []
    for i, item in enumerate(people):
        name = item["name"]
        quotes = "".join(f"<blockquote>{esc(span)}</blockquote>" for span in item["evidence"])
        people_html.append(
            f'<details class="person" id="person-{i}"{" open" if i == 0 else ""}>'
            f'<summary><span class="person-index">{i + 1:02d}</span>'
            f'<span class="person-name">{esc(name)}</span>'
            f'<span class="person-count">{item["age"]} 岁</span></summary>'
            f'<p class="relation">{esc(item["one_sentence"])}</p>'
            f'<article class="event"><p class="event-prose">{esc(item["event_description"])}</p>'
            f'<details class="evidence"><summary>查看原文依据</summary>{quotes}</details></article></details>'
        )
    digest = hashlib.sha256(source.encode()).hexdigest()[:12]
    page = PAGE.replace("__STORY__", story).replace("__JUMP__", jump)
    page = page.replace("__PEOPLE__", "\n".join(people_html))
    page = page.replace("__CAST_COUNT__", str(len(gold["people"])))
    page = page.replace("__EVENT_COUNT__", str(len(people)))
    page = page.replace("__HASH__", digest)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(page, "utf-8")
    return OUTPUT


PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="多人物交织叙事的正文与逐人互动事件对照">
  <title>交织日记｜人物事件验收</title>
  <style>
    :root { --paper:#eee9df; --sheet:#f8f4ea; --ink:#24251f; --soft:#6c7068; --line:#ccc7b9; --accent:#9c3e2c; --deep:#263834; }
    * { box-sizing:border-box; }
    html { scroll-behavior:smooth; }
    body { margin:0; background:var(--paper); color:var(--ink); font-family:"Songti SC","Noto Serif CJK SC",Georgia,serif; }
    body::before { content:""; position:fixed; inset:0; pointer-events:none; opacity:.24; background-image:radial-gradient(#8d826f 0.45px,transparent 0.45px); background-size:7px 7px; }
    a { color:inherit; }
    .mast { position:relative; z-index:2; background:var(--deep); color:#f2ead9; padding:30px clamp(22px,4vw,72px) 27px; display:grid; grid-template-columns:minmax(0,1fr) auto; gap:18px; align-items:end; }
    .eyebrow { margin:0 0 8px; color:#d3b9a0; font:600 11px/1.4 ui-monospace,SFMono-Regular,monospace; letter-spacing:.22em; }
    h1 { font-size:clamp(36px,4.7vw,72px); line-height:1.05; font-weight:500; letter-spacing:.065em; margin:0; }
    .sub { max-width:630px; color:#cfcfc4; margin:15px 0 0; line-height:1.75; font-size:14px; }
    .counts { display:flex; gap:22px; align-items:end; }
    .counts span { display:grid; gap:3px; min-width:72px; }
    .counts strong { font:400 35px/1 Georgia,serif; color:#e0aa8b; }
    .counts small { color:#cfcfc4; font-size:11px; letter-spacing:.08em; }
    .tools { position:relative; z-index:1; display:flex; flex-wrap:wrap; gap:10px 24px; padding:13px clamp(22px,4vw,72px); border-bottom:1px solid var(--line); font:600 12px/1.5 ui-monospace,SFMono-Regular,monospace; background:#e5dfd3; }
    .tools a { text-decoration:none; border-bottom:1px solid var(--accent); padding-bottom:2px; }
    .tools a:hover,.tools a:focus-visible { color:var(--accent); }
    .tools .hash { margin-left:auto; color:var(--soft); font-weight:400; }
    main { position:relative; display:grid; grid-template-columns:minmax(0,1.03fr) minmax(0,1fr); gap:0; max-width:1800px; margin:auto; min-height:calc(100vh - 185px); }
    .pane { min-width:0; padding:28px clamp(22px,3.7vw,66px) 70px; }
    .source { background:var(--sheet); border-right:1px solid var(--line); }
    .analysis { background:#e9e3d6; }
    .pane-head { display:flex; align-items:baseline; justify-content:space-between; gap:15px; border-bottom:1px solid var(--line); padding-bottom:13px; margin-bottom:26px; }
    h2 { margin:0; font-size:23px; font-weight:500; letter-spacing:.09em; }
    .pane-head span { color:var(--soft); font:11px/1.4 ui-monospace,SFMono-Regular,monospace; }
    .story { max-width:730px; margin:auto; font-size:16px; line-height:2.1; letter-spacing:.02em; }
    .story p { margin:0 0 1.6em; text-indent:2em; }
    .story p:first-child { text-indent:0; font-size:18px; color:var(--deep); border-left:3px solid var(--accent); padding-left:17px; }
    .story-present { background:#eee4d5; border-left:3px solid var(--accent); padding:14px 17px; text-indent:0!important; }
    .scope { margin:0 0 20px; color:var(--soft); font-size:13px; line-height:1.75; }
    .jump { display:flex; flex-wrap:wrap; gap:7px; margin:0 0 23px; }
    .jump a { text-decoration:none; padding:6px 9px; border:1px solid #c6c0b2; border-radius:2px; font-size:12px; background:#f1ecdf; }
    .jump a:hover,.jump a:focus-visible { border-color:var(--accent); color:var(--accent); }
    .person { border-top:1px solid #b9b4a9; padding:0; }
    .person:last-child { border-bottom:1px solid #b9b4a9; }
    .person summary { cursor:pointer; display:flex; gap:13px; align-items:baseline; list-style:none; padding:17px 0; }
    .person summary::-webkit-details-marker { display:none; }
    .person summary::after { content:"＋"; margin-left:8px; font-size:21px; line-height:1; color:var(--accent); }
    .person[open] summary::after { content:"−"; }
    .person-index { color:var(--accent); font:13px/1 ui-monospace,SFMono-Regular,monospace; }
    .person-name { font-size:24px; letter-spacing:.12em; }
    .person-count { margin-left:auto; color:var(--soft); font:11px/1.4 ui-monospace,SFMono-Regular,monospace; white-space:nowrap; }
    .relation { margin:0 0 13px 29px; color:#50564c; font-size:13px; line-height:1.7; }
    .event { margin:0 0 14px 29px; background:#f6f1e7; border:1px solid #d5cfc1; padding:15px 18px 14px; box-shadow:3px 3px 0 #dad3c6; }
    .event-prose { margin:0; font-size:14px; line-height:1.95; }
    .evidence summary { cursor:pointer; font-size:12px; color:var(--accent); }
    .event-top { display:flex; gap:10px; align-items:center; border-bottom:1px solid #ddd5c8; padding-bottom:10px; margin-bottom:10px; font:11px/1.2 ui-monospace,SFMono-Regular,monospace; }
    .event-number { color:var(--accent); font-weight:700; }
    .event-status { color:#f9f3e8; background:var(--deep); padding:4px 7px; }
    .event-scene { color:var(--soft); margin-left:auto; }
    dl { display:grid; grid-template-columns:42px 1fr; column-gap:10px; row-gap:7px; margin:0; font-size:13px; line-height:1.65; }
    dt { color:var(--accent); font-weight:700; } dd { margin:0; }
    .evidence { border-top:1px dashed #d0c7ba; margin-top:12px; padding-top:9px; }
    .evidence>span { font:10px/1.4 ui-monospace,SFMono-Regular,monospace; color:var(--soft); letter-spacing:.08em; }
    blockquote { margin:6px 0 0 0; padding-left:9px; border-left:2px solid #c6a993; color:#5e6057; font-size:12px; line-height:1.6; }
    footer { position:relative; padding:17px clamp(22px,4vw,72px) 25px; border-top:1px solid var(--line); font:11px/1.7 ui-monospace,SFMono-Regular,monospace; color:var(--soft); }
    @media (min-width:900px) { .pane { max-height:calc(100vh - 165px); overflow-y:auto; scrollbar-color:#c5bba9 transparent; } }
    @media (max-width:899px) { .mast { grid-template-columns:1fr; } main { grid-template-columns:1fr; } .analysis { order:-1; } .source { border-right:0; border-bottom:1px solid var(--line); } .counts { gap:30px; } .tools .hash { display:none; } }
    @media (max-width:560px) { .mast { padding-top:25px; } .pane { padding-bottom:42px; } .story { font-size:15px; } .event { margin-left:0; } .relation { margin-left:0; } }
  </style>
</head>
<body>
  <header class="mast">
    <div><p class="eyebrow">TEST DOSSIER / 01</p><h1>交织日记</h1><p class="sub">每个人物保留一句话身份，以及一段完整叙述其与陆闻的事件；右侧可展开核对原文。</p></div>
    <div class="counts"><span><strong>__CAST_COUNT__</strong><small>成年人物</small></span><span><strong>__EVENT_COUNT__</strong><small>事件长描述</small></span></div>
  </header>
  <nav class="tools" aria-label="页面导航与文档下载"><a href="#events">直达人物描述 ↓</a><a href="../多人物交织场景_输入.md">正文原文件 ↗</a><a href="../多人物交织场景_标准结构.json">结构化 JSON ↗</a><a href="../多人物交织场景_人物事件对照.md">长描述文档 ↗</a><span class="hash">SOURCE SHA256 __HASH__</span></nav>
  <main>
    <section class="pane source" id="source"><div class="pane-head"><h2>正文</h2><span>INPUT / NATURAL PROSE</span></div><div class="story">__STORY__</div></section>
    <section class="pane analysis" id="events"><div class="pane-head"><h2>人物与陆闻</h2><span>GOLD / EVENT NARRATIVES</span></div><p class="scope">每人一段连贯事件描述，约 300–400 字。当前接待室只有许澄和陆闻；回忆、想象及互斥分支分别说明。</p><nav class="jump" aria-label="跳转到人物">__JUMP__</nav>__PEOPLE__</section>
  </main>
  <footer>人工校对的标准答案 · 页面由 docs/test 的正文与 JSON 生成 · 可用原文依据逐条核验</footer>
</body>
</html>
"""


if __name__ == "__main__":
    print(render())

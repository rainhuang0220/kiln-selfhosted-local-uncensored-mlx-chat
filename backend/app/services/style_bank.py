"""Offstage style corpora (「以下括号里的全部内容仅作为风格参考（…）」) kept apart from the scene.

The parenthesis is not the current scene. Its names and events are stored as a StyleBank and
never merged into SceneGraph cast / contact / must_keep; only a short register + technique
digest reaches the model, in a labeled user-side fence. Regex/lexicon only, no model call.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from app.services.scene_graph import (
    _CJK,
    _INSTRUMENT_RE,
    _REGION_RE,
    _TOUCH_RE,
    HEADER,
    SceneGraph,
    _is_name,
)

DIGEST_CAP = 600
STYLE_ONLY_TURN = "（风格参考已收下，继续当前场面。）"
STYLE_FENCE_NOTE = "仅作文风与手法参考。风格参考里的人名与事件不在当前场面，禁止写进本场正文。"

_MARKER = re.compile(r"(?:风格|文风)参考|仅供参考")
_OPEN, _CLOSE = "（(", "）)"
_GAP = re.compile(r"[\s:：，,。]*")
_CLAUSE_START = re.compile(r"[，,。；;！!？?\n]")
_SENTENCE = re.compile(r"[^。！？!?\n]+")
_CLAUSE = re.compile(r"[^，,。；;！!？?、\n]+")
_LABEL = re.compile(r"(文风|风格|节奏|视角|语气|手法|技巧)[:：]\s*([^\n。]+)")
_NAME_SLOT = re.compile(
    rf"(?:^|(?<=[，,。；;！!？?、\s和与跟给对把被让替同叫]))([{_CJK}]{{2,3}}?)"
    r"(?=[是在把被将的和与跟说曾又总从给对替让去来也就都还只却便已正刚才后比每站坐靠趴拉帮教用递笑喝剪升辞搬寄开推握伸])"
)
_ROLE = re.compile(
    r"(学姐|学长|学妹|前任|邻居|上司|老板|同事|室友|网友|教练|摄影师|老师|学生|客人|情人|丈夫|妻子|男友|女友|"
    r"闺蜜|表姐|表妹|姐姐|妹妹|哥哥|弟弟|朋友|房东|医生|护士|店主|花店老板|技师)"
)
_CITIES = (
    "北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "重庆", "武汉", "苏州", "厦门", "青岛",
    "西安", "天津", "长沙", "昆明", "大理", "三亚", "香港", "台北", "东京", "首尔",
)
_WHEN = re.compile(r"(那年|那天|那晚|那周|第二年|后来|春天|夏天|秋天|冬天|周末|傍晚|凌晨|雨夜|年会|毕业)")
_NOT_NAME_HEAD = set("那这每有某第上下去今明昨前后半整满两几")
_NOT_NAME_TAIL = set("天年夜里边时次个州京海城市镇村路街楼店馆院室房岛湖山")
# Pronouns / role nouns / function words that _NAME_SLOT can still catch once.
_STOP_NAMES = frozenset(
    {
        "她", "他", "你", "我", "们", "技师", "客人", "没有", "什么", "自己", "对方",
        "两人", "彼此", "那里", "这里", "现在", "然后", "继续", "慢慢", "轻轻", "一下",
    }
)
_REGISTER_LEXICON = (
    ("第一人称", "第一人称"), ("第二人称", "第二人称"), ("第三人称", "第三人称"),
    ("短句", "短句"), ("长句", "长句"), ("白描", "白描"), ("口语", "口语"),
    ("慢节奏|慢慢|缓缓", "慢节奏"), ("急促|快节奏", "快节奏"),
    ("露骨|直白", "直白"), ("含蓄|克制", "克制"), ("呼吸|喘", "写呼吸"), ("温度|烫|凉", "写温度"),
)


@dataclass
class StyleSplit:
    live: str
    corpus: str
    marker: str = ""


def _match_forward(text: str, start: int) -> int:
    depth = 0
    for i in range(start, len(text)):
        if text[i] in _OPEN:
            depth += 1
        elif text[i] in _CLOSE:
            depth -= 1
            if depth == 0:
                return i
    last = max(text.rfind(c) for c in _CLOSE)
    return last if last > start else len(text)


def _match_backward(text: str, end: int) -> int:
    depth = 0
    for i in range(end, -1, -1):
        if text[i] in _CLOSE:
            depth += 1
        elif text[i] in _OPEN:
            depth -= 1
            if depth == 0:
                return i
    first = min((text.find(c) for c in _OPEN if c in text), default=-1)
    return first if 0 <= first < end else 0


def _split_once(text: str) -> StyleSplit | None:
    for m in _MARKER.finditer(text):
        head = max((c.end() for c in _CLAUSE_START.finditer(text, 0, m.start())), default=0)
        gap = _GAP.match(text, m.end())
        at = gap.end() if gap else m.end()
        if at < len(text) and text[at] in _OPEN:
            close = _match_forward(text, at)
            corpus = text[at + 1: close]
            live = text[:head] + text[close + 1:]
        else:
            before = text[:head].rstrip(" \n:：，,。")
            if not before or before[-1] not in _CLOSE:
                continue
            open_at = _match_backward(before, len(before) - 1)
            corpus = before[open_at + 1: -1]
            live = text[:open_at] + text[m.end():]
        if corpus.strip():
            return StyleSplit(live=live, corpus=corpus.strip(), marker=text[head: m.end()].strip())
    return None


def split_style_corpus(text: str) -> StyleSplit:
    """Split a user turn into the live directive and the marked 风格参考 parenthesis (head or tail)."""
    live, corpora, markers = text or "", [], []
    for _ in range(3):
        split = _split_once(live)
        if split is None:
            break
        live, corpora, markers = split.live, [*corpora, split.corpus], [*markers, split.marker]
    if not corpora:
        return StyleSplit(live=text or "", corpus="")
    live = re.sub(r"\n{3,}", "\n\n", live).strip().rstrip("，,；;：:")
    return StyleSplit(live=live, corpus="\n".join(corpora), marker=markers[0])


@dataclass
class StyleName:
    name: str
    role_hint: str = ""
    do_not_enter_scene: bool = True


@dataclass
class StyleEvent:
    label: str
    who: list[str] = field(default_factory=list)
    gist: str = ""


def _uniq(items: Iterable[str], cap: int) -> list[str]:
    out: list[str] = []
    for item in items:
        key = (item or "").strip()
        if key and key not in out:
            out.append(key)
    return out[:cap]


def _name_candidates(corpus: str, *, blocked: Iterable[str] = ()) -> list[str]:
    """Proper-name candidates. Once is enough; stoplist + live names stay out."""
    blocked_set = {b for b in blocked if b}
    counts: Counter[str] = Counter()
    for clause in _CLAUSE.finditer(corpus):
        for m in _NAME_SLOT.finditer(clause.group(0)):
            counts[m.group(1)] += 1
    for m in re.finditer(rf"([{_CJK}]{{2,3}})是(?:她|他|我|你)?的?{_ROLE.pattern}", corpus):
        counts[m.group(1)] += 0  # ensure intro names appear even without a slot hit
        counts[m.group(1)] = max(counts[m.group(1)], 1)
    out = []
    for cand, n in counts.most_common():
        if n < 1:
            continue
        if cand in _STOP_NAMES or cand in blocked_set:
            continue
        if cand[0] in _NOT_NAME_HEAD or cand[-1] in _NOT_NAME_TAIL or cand in _CITIES:
            continue
        if not _is_name(cand) or _TOUCH_RE.search(cand) or _INSTRUMENT_RE.fullmatch(cand):
            continue
        if any(cand != o and cand in o for o in counts if counts[o] >= n):
            continue
        out.append(cand)
    return out[:24]


def scrub_prose(text: str, names: Iterable[str]) -> str:
    """Delete StyleBank name spans from assistant prose (same-hop intercept)."""
    out = text or ""
    ordered = sorted({n for n in names if n and n in out}, key=len, reverse=True)
    for name in ordered:
        out = out.replace(name, "")
    out = re.sub(r"[（(][）)]", "", out)
    out = re.sub(r"的{2,}", "的", out)
    out = re.sub(r"[，,]{2,}", "，", out)
    out = re.sub(r"[。！？!?]{2,}", lambda m: m.group(0)[0], out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out


@dataclass
class StyleBank:
    names: list[StyleName] = field(default_factory=list)
    events: list[StyleEvent] = field(default_factory=list)
    register: list[str] = field(default_factory=list)
    techniques: list[str] = field(default_factory=list)
    digest: str = ""

    # ---- persistence -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "StyleBank":
        data = data if isinstance(data, dict) else {}
        bank = cls(
            names=[
                StyleName(str(n["name"]), str(n.get("role_hint") or ""))
                for n in data.get("names") or []
                if isinstance(n, dict) and n.get("name")
            ],
            events=[
                StyleEvent(str(e.get("label") or ""), [str(w) for w in e.get("who") or []], str(e.get("gist") or ""))
                for e in data.get("events") or []
                if isinstance(e, dict)
            ],
            register=[str(x) for x in data.get("register") or []],
            techniques=[str(x) for x in data.get("techniques") or []],
        )
        bank.digest = bank.render_digest()
        return bank

    def is_empty(self) -> bool:
        return not (self.names or self.events or self.register or self.techniques)

    # ---- extraction --------------------------------------------------
    @classmethod
    def from_corpus(cls, corpus: str) -> "StyleBank":
        bank = cls()
        bank.absorb(corpus)
        return bank

    def absorb(self, corpus: str, *, blocked: Iterable[str] = ()) -> "StyleBank":
        text = corpus or ""
        known = {n.name for n in self.names}
        for name in _name_candidates(text, blocked=blocked):
            if name in known:
                continue
            role = re.search(rf"{re.escape(name)}是(?:她|他|我|你)?的?{_ROLE.pattern}", text)
            self.names.append(StyleName(name, role.group(1) if role else ""))
            known.add(name)
        self.names = self.names[:24]
        names = [n.name for n in self.names]
        for s in _SENTENCE.finditer(text):
            sent = s.group(0).strip()
            who = [n for n in names if n in sent]
            city = next((c for c in _CITIES if c in sent), "")
            when = _WHEN.search(sent)
            if not who or not (city or when):
                continue
            label = f"{who[0]}·{city or when.group(1)}"
            if any(e.label == label for e in self.events):
                continue
            self.events.append(StyleEvent(label, who, sent[:40]))
        self.events = self.events[:16]
        labeled_reg, labeled_tech = [], []
        for m in _LABEL.finditer(text):
            items = [x.strip() for x in re.split(r"[，,、；;]", m.group(2)) if 2 <= len(x.strip()) <= 16]
            (labeled_tech if m.group(1) in {"手法", "技巧"} else labeled_reg).extend(items)
        derived = [tag for rx, tag in _REGISTER_LEXICON if re.search(rx, text)]
        self.register = _uniq([*self.register, *labeled_reg, *derived], 10)
        moves = []
        for c in _CLAUSE.finditer(text):
            clause = c.group(0).strip()
            if not 4 <= len(clause) <= 18 or any(n in clause for n in names) or _WHEN.search(clause):
                continue
            subject = _NAME_SLOT.match(clause)
            if subject and _is_name(subject.group(1)):
                continue
            inst = _INSTRUMENT_RE.search(clause)
            if _TOUCH_RE.search(clause) or _REGION_RE.search(clause) or (inst and inst.group(0) != "手"):
                moves.append(clause)
        self.techniques = _uniq([*self.techniques, *labeled_tech, *moves], 14)
        self.scrub()
        self.digest = self.render_digest()
        return self

    def update(self, other: "StyleBank") -> "StyleBank":
        known = {n.name for n in self.names}
        self.names = [*self.names, *(n for n in other.names if n.name not in known)][:24]
        labels = {e.label for e in self.events}
        self.events = [*self.events, *(e for e in other.events if e.label not in labels)][:16]
        self.register = _uniq([*self.register, *other.register], 10)
        self.techniques = _uniq([*self.techniques, *other.techniques], 14)
        self.scrub()
        self.digest = self.render_digest()
        return self

    def scrub(self) -> None:
        names = [n.name for n in self.names]
        self.register = [r for r in self.register if not any(n in r for n in names)]
        self.techniques = [t for t in self.techniques if not any(n in t for n in names)]

    def scrub_prose(self, text: str, *, live_texts: Iterable[str] = ()) -> str:
        """Same-hop: strip offstage bank names from assistant prose; keep live cast."""
        return scrub_prose(text, self.offstage(live_texts))

    # ---- render ------------------------------------------------------
    def render_digest(self) -> str:
        out = ""
        for head, items, sep in (("文风：", self.register, "、"), ("手法：", self.techniques, "；")):
            line = ""
            for item in items:
                nxt = f"{line}{sep if line else head}{item}"
                if len(out) + len(nxt) + 1 > DIGEST_CAP:
                    break
                line = nxt
            if line:
                out = f"{out}\n{line}" if out else line
        return out

    def fence(self) -> str | None:
        if not self.digest:
            return None
        return f"<style_bank>\n{HEADER}\n{STYLE_FENCE_NOTE}\n{self.digest}\n</style_bank>"

    def offstage(self, live_texts: Iterable[str]) -> set[str]:
        """Bank names no live directive has put on stage."""
        live = "\n".join(live_texts)
        return {n.name for n in self.names if n.name not in live}


def _live_name_blocklist(live: str) -> set[str]:
    """阿沈-class names already on stage in the live directive must not enter the bank."""
    blocked = set(_STOP_NAMES)
    for m in re.finditer(rf"([{_CJK}]{{2,3}})", live or ""):
        cand = m.group(1)
        if _is_name(cand) and cand not in _STOP_NAMES:
            blocked.add(cand)
    for role in ("技师", "客人"):
        for m in re.finditer(rf"{role}([{_CJK}]{{2,3}})", live or ""):
            blocked.add(m.group(1))
    return blocked


def ingest_history(history: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], StyleBank, list[str]]:
    """Replace each user turn by its live directive; collect the parentheses into one StyleBank."""
    bank = StyleBank()
    live_texts: list[str] = []
    out: list[dict[str, Any]] = []
    for msg in history:
        if msg.get("role") == "user":
            split = split_style_corpus(msg.get("content") or "")
            if split.corpus:
                bank.absorb(split.corpus, blocked=_live_name_blocklist(split.live))
                msg = {**msg, "content": split.live or STYLE_ONLY_TURN}
            live_texts.append(split.live)
        out.append(msg)
    return out, bank, live_texts


def mentions(text: str, names: Iterable[str]) -> bool:
    return any(n and n in (text or "") for n in names)


def evict_offstage(graph: SceneGraph, blocked: set[str]) -> SceneGraph:
    """Drop offstage people from every on-stage slot (cast, contact, positions, pins)."""
    if not blocked:
        return graph
    graph.cast = [m for m in graph.cast if m.name not in blocked]
    graph.contact = [c for c in graph.contact if c.who not in blocked and c.target not in blocked]
    graph.space.relative_positions = [p for p in graph.space.relative_positions if not mentions(p, blocked)]
    graph.must_keep = [k for k in graph.must_keep if not mentions(k, blocked)]
    graph.fresh = [a for a in graph.fresh if not mentions(a, blocked)]
    if graph.focus in blocked:
        graph.focus = ""
    if graph.actor in blocked:
        graph.actor = ""
    return graph

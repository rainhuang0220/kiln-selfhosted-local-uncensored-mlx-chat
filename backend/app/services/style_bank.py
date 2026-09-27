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
STYLE_FENCE_NOTE = (
    "已确认背景与明确偏好可用于角色回应；其余只作文风与手法参考。"
    "参考人物与事件不在当前场面；参考情节此刻未发生，勿复述参考正文；"
    "背景中提及某人不表示此人在场。"
)

_MARKER = re.compile(r"(?:风格|文风)参考|仅供参考")
# A user may give the current scene in one sentence and then paste a long,
# unbracketed background/fantasy reference.  Its source scope must be decided
# before SceneGraph, facts, lore activation, or prompt packing see the text.
# Natural markers include the owner line 「以下内容是我的信息背景和性癖参考，
# 或者幻想参考。」 plus bare heads 信息背景 / 性癖参考 / 幻想参考 / 以下内容是,
# with or without a following （…） / (...).
_FREE_REFERENCE = re.compile(
    r"(?:"
    r"(?:以下|下面|接下来)[^\n。！？:：]{0,100}(?:参考|素材)"
    r"|"
    r"(?:我的)?(?:信息背景|性癖参考|性瘾参考|幻想参考)"
    r"|"
    r"以下内容是"
    r")"
    r"(?:[（(][^）\n]{0,80}[）)])?"
    r"[^\n。！？:：]{0,40}[。！？:：]?"
)
_OFFSTAGE_CUE = re.compile(r"背景|幻想|风格|文风|素材|资料|人设|性癖|性瘾|参考|以下内容是")
_RETURN_TO_SCENE = re.compile(
    r"(?:^|\n|(?<=[。！？]))\s*(?:请)?(?:回到|返回|切回|现在回到|当前场景|本场|你是|我们现在)",
    re.MULTILINE,
)
_OPEN, _CLOSE = "（(", "）)"
_GAP = re.compile(r"[\s:：，,。]*")
_CLAUSE_START = re.compile(r"[，,。；;！!？?\n]")
_SENTENCE = re.compile(r"[^。！？!?\n]+")
_CLAUSE = re.compile(r"[^，,。；;！!？?、\n]+")
_LABEL = re.compile(r"(文风|风格|节奏|视角|语气|手法|技巧)[:：]\s*([^\n。]+)")
_BACKGROUND_LABEL = re.compile(r"^(?:现实背景|真实背景|个人背景|个人信息|我的信息背景|背景事实)\s*[:：]\s*(.+)$")
_PREFERENCE_LABEL = re.compile(r"^(?:偏好|喜好|明确偏好|我的偏好|我的性癖|边界|雷点)\s*[:：]\s*(.+)$")
_SCENE_ENTRY_VERB = re.compile(r"(?:推开.{0,6}门|走进|走入|进门|来到|出现|进入|在场|走到|站在|坐在)")
_SCENE_SWITCH_VERB = re.compile(r"(?:切到|切回|转到|换到|让|叫|请)(?:.{0,16})$")
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


def _split_free_reference(text: str) -> StyleSplit | None:
    """Split an explicitly labeled, unbracketed reference from the live turn.

    A trailing current-scene instruction is promoted only when it has an
    explicit return cue near the end. Ambiguous reference prose stays offstage.
    """
    for marker in _FREE_REFERENCE.finditer(text):
        label = marker.group(0)
        if not _OFFSTAGE_CUE.search(label):
            continue
        start = marker.end()
        tail = text[start:]
        if not tail.strip():
            continue
        return_at = None
        for match in _RETURN_TO_SCENE.finditer(tail):
            if match.start() >= 200 and len(tail) - match.start() <= 400:
                return_at = match.start()
        corpus = tail[:return_at] if return_at is not None else tail
        live = text[:marker.start()] + (tail[return_at:] if return_at is not None else "")
        if corpus.strip():
            return StyleSplit(live=live.strip(), corpus=corpus.strip(), marker=label.strip())
    return None


def split_style_corpus(text: str) -> StyleSplit:
    """Split explicit offstage reference material from a live user turn."""
    live, corpora, markers = text or "", [], []
    for _ in range(3):
        split = _split_once(live) or _split_free_reference(live)
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


def split_reference_claims(corpus: str) -> tuple[list[str], list[str], str]:
    """Promote only explicitly labeled real facts and preferences from a reference."""
    facts: list[str] = []
    preferences: list[str] = []
    remaining: list[str] = []
    for line in (corpus or "").splitlines():
        stripped = line.strip()
        fact = _BACKGROUND_LABEL.match(stripped)
        preference = _PREFERENCE_LABEL.match(stripped)
        if fact:
            facts.append(fact.group(1).strip().rstrip("。！？"))
        elif preference:
            preferences.append(preference.group(1).strip().rstrip("。！？"))
        else:
            remaining.append(line)
    return _uniq(facts, 12), _uniq(preferences, 12), "\n".join(remaining)


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


class OffstageStreamFilter:
    """Hold incomplete name prefixes so a streamed delta cannot reveal a bank name."""

    def __init__(self, names: Iterable[str] = ()) -> None:
        self.names = sorted({str(name) for name in names if name}, key=len, reverse=True)
        self.pending = ""

    def set_names(self, names: Iterable[str]) -> None:
        self.names = sorted({str(name) for name in names if name}, key=len, reverse=True)

    def _drain(self, *, final: bool) -> str:
        out: list[str] = []
        while self.pending:
            hit = next((name for name in self.names if self.pending.startswith(name)), None)
            if hit:
                self.pending = self.pending[len(hit):]
                continue
            if not final and any(name.startswith(self.pending) for name in self.names):
                break
            out.append(self.pending[0])
            self.pending = self.pending[1:]
        return "".join(out)

    def feed(self, chunk: str) -> str:
        if not self.names:
            return chunk
        self.pending += chunk
        return self._drain(final=False)

    def flush(self) -> str:
        return self._drain(final=True)


@dataclass
class StyleBank:
    names: list[StyleName] = field(default_factory=list)
    events: list[StyleEvent] = field(default_factory=list)
    register: list[str] = field(default_factory=list)
    techniques: list[str] = field(default_factory=list)
    background_facts: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
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
            background_facts=[str(x) for x in data.get("background_facts") or []],
            preferences=[str(x) for x in data.get("preferences") or []],
        )
        bank.scrub()
        bank.digest = bank.render_digest()
        return bank

    def is_empty(self) -> bool:
        return not (self.names or self.events or self.register or self.techniques or self.background_facts or self.preferences)

    # ---- extraction --------------------------------------------------
    @classmethod
    def from_corpus(cls, corpus: str) -> "StyleBank":
        bank = cls()
        bank.absorb(corpus)
        return bank

    def absorb(self, corpus: str, *, blocked: Iterable[str] = ()) -> "StyleBank":
        facts, preferences, text = split_reference_claims(corpus)
        self.background_facts = _uniq([*self.background_facts, *facts], 12)
        self.preferences = _uniq([*self.preferences, *preferences], 12)
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
        self.background_facts = _uniq([*self.background_facts, *other.background_facts], 12)
        self.preferences = _uniq([*self.preferences, *other.preferences], 12)
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
        for head, items, sep in (
            ("已确认背景：", self.background_facts, "；"),
            ("明确偏好：", self.preferences, "；"),
            ("文风：", self.register, "、"),
            ("手法：", self.techniques, "；"),
        ):
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

    def offstage_scene(self, live_texts: Iterable[str]) -> set[str]:
        """A question about a reference person does not make them present."""
        texts = list(live_texts)
        blocked = set()
        for person in self.names:
            name = person.name
            staged = False
            for text in texts:
                for clause in re.split(r"[，,。！？!?；;\n]", text or ""):
                    at = clause.find(name)
                    if at < 0:
                        continue
                    before, after = clause[:at], clause[at + len(name):]
                    if _SCENE_ENTRY_VERB.search(after[:30]) or _SCENE_SWITCH_VERB.search(before[-18:]):
                        staged = True
                        break
                if staged:
                    break
            if not staged:
                blocked.add(name)
        return blocked


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

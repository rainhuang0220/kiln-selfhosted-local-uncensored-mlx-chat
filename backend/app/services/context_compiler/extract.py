"""Studio long-paste people extract: 9B first (Stage A), rules second (Stage B).

Stage A sends the live lock plus whole reference paragraphs (1200–1800 chars,
200 overlap) to the chat model and asks for people[] JSON. Stage B never
proposes people ahead of the model: it keeps, folds, or drops what the model
returned and grounds every identity to a clause the source attaches to that
exact name. Stage B only drops a person or blanks a field; it never adds a
name, a job, or an event. Chat send never reaches this module.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

from app.providers.base import ChatRequest

from .alias import FOLDABLE, GENERIC_SOCIAL, is_alias_or_role, rules_alias_map

EXTRACT_SYSTEM = """你是人物资料编译器，不是写作者。只根据用户给出的原文做抽取。
只输出一个 JSON 对象，不要解释，不要 markdown。

规则：
1. people[].name 必须是原文里逐字出现的人名（2–4 个汉字的专名）。
2. 禁止把称呼写成人物：他、她、姐姐、妈妈、宝宝、闺蜜、老师、队长、校医、顾客、技师。
3. 称呼放进该人的 aliases。例如 陆遥.aliases 可含「姐姐」。
4. identity 只用原文里紧挨着这个人名的身份/职业/关系，不超过 16 字。原文没写就留空。禁止把隔壁人的职业安到这个人身上。
5. one_event 用原文里这个人做过的一件事，不超过 40 字，必须能在原文找到。
6. 禁止发明原文没有的人名、职业、事件。
7. 当前店内/接待室里的人标 present=true，其他人 false。

格式：
{"people":[{"name":"","aliases":[],"identity":"","one_event":"","present":false}]}"""

WINDOW_MAX = 1800
WINDOW_MIN = 1200
WINDOW_OVERLAP = 200
LIVE_LOCK_MAX = 200
# mlx-lm runs with decode concurrency 1, so windows queue; each gets its own clock.
# Total stays under the 180 s nginx read timeout on /context/presets/preview.
WINDOW_TIMEOUT_S = 75.0
TOTAL_CAP_S = 170.0
MAX_TOKENS = 1200
MAX_ROWS = 16

_CLAUSE_END = re.compile(r"[。！？!?；;\n]")
_SENTENCE_END = re.compile(r"[。！？!?\n]")
# Blood/family kinship only binds by apposition (姐姐陆遥 / 林栀是她妹妹), never by proximity.
_KIN = frozenset(
    {
        "姐姐", "哥哥", "妹妹", "弟弟", "妈妈", "爸爸", "母亲", "父亲", "表姐", "表妹",
        "表哥", "表弟", "姑姑", "舅舅", "阿姨", "叔叔", "奶奶", "爷爷", "外婆", "外公",
        "嫂子", "姐夫", "大姐", "二姐", "小妹",
    }
)
_ROLE_WORDS = (FOLDABLE - _KIN) | frozenset(
    {"店长", "职员", "经理", "记者", "助理", "教练", "管理员", "工程师", "助教", "同桌", "策展人", "队员"}
)
_KIN_ALT = "|".join(sorted(_KIN, key=len, reverse=True))
_EDGE = "的了着在与和及跟把被是，,。；;、"


# Stage A ----------------------------------------------------------------------


def live_lock(live: str) -> str:
    return re.sub(r"\s+", " ", live or "").strip()[:LIVE_LOCK_MAX]


def _last_break(text: str, lo: int, hi: int) -> int:
    """Index just after the last sentence end in text[lo:hi]; -1 when none."""
    best = -1
    for match in _SENTENCE_END.finditer(text, lo, hi):
        best = match.end()
    return best


def reference_windows(reference: str) -> list[str]:
    """Whole reference paragraphs in 1200–1800 char windows with ~200 overlap."""
    text = (reference or "").strip()
    if not text:
        return []
    if len(text) <= WINDOW_MAX:
        return [text]
    count = -(-(len(text) - WINDOW_OVERLAP) // (WINDOW_MAX - WINDOW_OVERLAP))
    target = -(-(len(text) + (count - 1) * WINDOW_OVERLAP) // count)
    target = min(WINDOW_MAX, max(WINDOW_MIN, target))
    windows: list[str] = []
    start = 0
    while True:
        end = min(len(text), start + target)
        if len(text) - end < WINDOW_OVERLAP:
            end = len(text)
        if end < len(text):
            snapped = _last_break(text, start + int(target * 0.75), end)
            if snapped > start:
                end = snapped
        windows.append(text[start:end].strip())
        if end >= len(text):
            return windows
        nxt = end - WINDOW_OVERLAP
        snapped = _last_break(text, max(start + 1, end - 2 * WINDOW_OVERLAP), nxt)
        start = snapped if snapped > start else nxt


def build_extract_user(lock: str, window: str, index: int, total: int) -> str:
    # Content hints only. A compact/one-line JSON hint makes this 9B loop on aliases.
    hint = "「我」是用户本人，不要作为 people 输出。"
    if index > 1:
        hint += "live 里的人已在第 1 段抽取，这里只输出 reference 里出现的人物。"
    return (
        f"<live>{lock}</live>\n"
        f"<reference part=\"{index}/{total}\">\n{window}\n</reference>\n"
        f"{hint}只根据以上原文抽取人物，输出 JSON。"
    )


def extract_request(lock: str, window: str, index: int, total: int) -> ChatRequest:
    return ChatRequest(
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": build_extract_user(lock, window, index, total)},
        ],
        temperature=0.0,
        top_p=0.8,
        top_k=20,
        max_tokens=MAX_TOKENS,
        enable_thinking=False,
    )


def parse_people(model_text: str) -> list[dict[str, Any]] | None:
    """people[] from the model; salvage complete objects from a truncated array."""
    text = model_text or ""
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        payload = json.loads(text[start:end])
        if isinstance(payload, dict) and isinstance(payload.get("people"), list):
            return [p for p in payload["people"] if isinstance(p, dict)]
    except (ValueError, json.JSONDecodeError):
        pass
    marker = re.search(r'"people"\s*:\s*\[', text)
    if marker is None:
        return None
    decoder = json.JSONDecoder()
    at, people = marker.end(), []
    while at < len(text):
        while at < len(text) and text[at] in " \t\r\n,":
            at += 1
        if at >= len(text) or text[at] != "{":
            break
        try:
            item, at = decoder.raw_decode(text, at)
        except json.JSONDecodeError:
            break
        if isinstance(item, dict):
            people.append(item)
    return people


@dataclass
class StageA:
    windows: list[str]
    people: list[dict[str, Any]] = field(default_factory=list)
    ok_windows: int = 0
    errors: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0

    @property
    def ran(self) -> bool:
        return self.ok_windows > 0


async def run_stage_a(
    live: str,
    reference: str,
    complete: Callable[[ChatRequest], Awaitable[Any]],
    *,
    window_timeout_s: float = WINDOW_TIMEOUT_S,
    total_cap_s: float = TOTAL_CAP_S,
) -> StageA:
    """One 9B extract per reference window, in order.

    The local server decodes one request at a time, so concurrent windows only
    queue and the later ones time out while waiting. Sequential windows each get
    a full per-window timeout inside the total cap.
    """
    lock = live_lock(live)
    windows = reference_windows(reference) or ([lock] if lock else [])
    result = StageA(windows=windows)
    started = time.monotonic()

    for index, window in enumerate(windows):
        remaining = total_cap_s - (time.monotonic() - started)
        if remaining <= 1.0:
            result.errors.append(f"window {index + 1}: total cap {total_cap_s:.0f}s reached")
            continue
        request = extract_request(lock, window, index + 1, len(windows))
        try:
            answer = await asyncio.wait_for(complete(request), timeout=min(window_timeout_s, remaining))
        except Exception as exc:  # timeout, Hub error, connection refused
            result.errors.append(f"window {index + 1}: {type(exc).__name__}: {str(exc)[:160]}")
            continue
        people = parse_people(getattr(answer, "content", None) or str(answer))
        if people is None:
            result.errors.append(f"window {index + 1}: no people JSON")
            continue
        result.ok_windows += 1
        for person in people[:32]:
            result.people.append({**person, "_window": index})
    result.elapsed_s = time.monotonic() - started
    return result


# Stage B ----------------------------------------------------------------------


class _Attachment:
    """Which proper name does the source attach a span to?

    In-clause names win by distance; the narrator only claims a span it touches
    (顾客陆闻). A clause with no name belongs to the last named subject in the
    paragraph (她三十一岁，是队长 → 唐宁), else to a following 她叫X.
    """

    def __init__(self, source: str, names: Iterable[str], narrator: str = ""):
        self.text = source
        self.narrator = narrator
        self.names = sorted({n for n in names if n}, key=len, reverse=True)
        self.clauses: list[tuple[int, int, int]] = []
        para, start = 0, 0
        for match in _CLAUSE_END.finditer(source):
            self.clauses.append((start, match.end(), para))
            if match.group() == "\n":
                para += 1
            start = match.end()
        if start < len(source):
            self.clauses.append((start, len(source), para))
        taken = [False] * len(source)
        mentions = []
        for name in self.names:
            for match in re.finditer(re.escape(name), source):
                if any(taken[match.start():match.end()]):
                    continue
                for i in range(match.start(), match.end()):
                    taken[i] = True
                mentions.append((match.start(), match.end(), name))
        self.mentions = sorted(mentions)

    def _clause_at(self, at: int) -> int:
        for index, (start, end, _) in enumerate(self.clauses):
            if start <= at < end:
                return index
        return len(self.clauses) - 1

    def owner(self, start: int, end: int) -> str | None:
        if not self.clauses:
            return None
        index = self._clause_at(start)
        c_start, c_end, para = self.clauses[index]
        candidates = []
        for m_start, m_end, name in self.mentions:
            if m_end <= c_start or m_start >= c_end:
                continue
            gap = max(m_start - end, start - m_end, 0)
            if name == self.narrator and gap > 2:
                continue
            candidates.append((gap, m_start, name))
        if candidates:
            return min(candidates)[2]
        for m_start, _m_end, name in reversed(self.mentions):
            if m_start >= c_start:
                continue
            if self.clauses[self._clause_at(m_start)][2] != para:
                break
            if name != self.narrator:
                return name
        if index + 1 < len(self.clauses) and self.clauses[index + 1][2] == para:
            n_start, n_end, _ = self.clauses[index + 1]
            head = self.text[n_start:n_end]
            for name in self.names:
                if re.match(rf"\s*(?:她|他)?(?:叫|名叫){re.escape(name)}", head):
                    return name
        return None

    def same_paragraph(self, a: str, b: str) -> bool:
        paras = {}
        for m_start, _m_end, name in self.mentions:
            paras.setdefault(name, set()).add(self.clauses[self._clause_at(m_start)][2])
        return bool(paras.get(a, set()) & paras.get(b, set()))


class _Grounder:
    def __init__(self, source: str, names: Iterable[str], narrator: str, aliases: dict[str, str]):
        self.source = source
        self.narrator = narrator
        self.aliases = aliases
        self.names = {n for n in names if n}
        self.attach = _Attachment(source, self.names | ({narrator} if narrator else set()), narrator)

    def _variants(self, text: str) -> list[str]:
        out = [text]
        if self.narrator and self.narrator in text:
            out.append(text.replace(self.narrator, "我"))
        for alias, owner in self.aliases.items():
            for base in list(out):
                if owner in base:
                    out.append(base.replace(owner, alias))
        return list(dict.fromkeys(v for v in out if len(v) >= 2))

    def owned(self, text: str, name: str, *, clause_ok: bool = False) -> str | None:
        """Source form of text whose occurrence the source attaches to name."""
        for variant in self._variants(text):
            for match in re.finditer(re.escape(variant), self.source):
                if self.attach.owner(match.start(), match.end()) == name:
                    return variant
                if clause_ok:
                    c_start, c_end, _ = self.attach.clauses[self.attach._clause_at(match.start())]
                    if name in self.source[c_start:c_end]:
                        return variant
        return None

    def kin_apposition(self, name: str, kin: str) -> bool:
        n, k = re.escape(name), re.escape(kin)
        return bool(
            re.search(rf"{k}(?:是|叫|名叫)?{n}", self.source)
            or re.search(rf"{n}(?:就是|是)(?:她|他|我|你)?的?{k}", self.source)
        )

    def _fold_kin(self, part: str, name: str) -> str:
        """比姐姐小一岁 → 比陆遥小一岁 when 姐姐 folds onto someone else."""
        for alias, owner in self.aliases.items():
            if owner != name and alias in _KIN:
                part = part.replace(alias, owner)
        return part

    def _other_ok(self, other: str, name: str) -> bool:
        if not other or other == name:
            return False
        if other == self.narrator:
            return True
        return other in self.names and self.attach.same_paragraph(other, name)

    def _part(self, part: str, name: str) -> str:
        part = re.sub(r"^(?:是|为|作为|担任)", "", part.strip())
        part = re.sub(r"的(?:那个)?人$", "", part)
        if len(part) < 2 or part == name:
            return ""
        for alias, owner in self.aliases.items():
            if owner != name:
                part = part.replace(f"{alias}的", f"{owner}的")
        kin = next((k for k in re.findall(_KIN_ALT, part) if f"{k}的" not in part), None)
        if kin:
            if not self.kin_apposition(name, kin):
                return ""
            possessive = re.fullmatch(rf"(.{{2,4}}?)的{re.escape(kin)}", part)
            if part == kin or (possessive and self._other_ok(possessive.group(1), name)):
                return part
            return kin
        if self.owned(part, name):
            return self._fold_kin(part, name)
        possessive = re.fullmatch(r"(.{2,4}?)的(.{2,})", part)
        if possessive and self._other_ok(possessive.group(1), name) and self.owned(possessive.group(2), name):
            return part
        for size in range(len(part) - 1, 2, -1):
            for at in range(0, len(part) - size + 1):
                piece = part[at:at + size]
                if piece[0] in _EDGE or piece[-1] in _EDGE:
                    continue
                if name not in piece and not is_alias_or_role(piece) and self.owned(piece, name):
                    return piece
        for word in sorted(_ROLE_WORDS, key=len, reverse=True):
            if word in part and self.owned(word, name):
                return word
        return ""

    def identity(self, raw: str, name: str) -> str:
        kept: list[str] = []
        for part in re.split(r"[；;、/，,]+", str(raw or "")):
            grounded = self._part(part, name)
            if grounded and not any(grounded in prev for prev in kept):
                kept = [prev for prev in kept if prev not in grounded] + [grounded]
        out = ""
        for piece in kept:
            if len(out) + len(piece) + (1 if out else 0) > 24:
                break
            out = f"{out}；{piece}" if out else piece
        return out

    def event(self, raw: str, name: str) -> str:
        text = re.sub(r"\s+", "", str(raw or ""))[:40].rstrip("。")
        if len(text) < 4:
            return ""
        return text if self.owned(text, name, clause_ok=True) else ""


def _cjk_name(token: str) -> bool:
    return 2 <= len(token) <= 4 and all("\u4e00" <= ch <= "\u9fff" for ch in token)


def ground_people(
    source: str,
    stage_a: StageA,
    *,
    name_ok: Callable[[str], bool],
    narrator: str = "",
    avatar: str = "",
) -> dict[str, Any]:
    """Keep, fold, or drop Stage A people; blank a field the source did not attach."""
    text = source or ""
    order: list[str] = []
    proposals: dict[str, list[dict[str, Any]]] = {}
    dropped: list[str] = []
    for person in stage_a.people:
        name = str(person.get("name") or "").strip()
        if (
            not _cjk_name(name)
            or name not in text
            or is_alias_or_role(name)
            or name == narrator
            or (avatar and name in avatar)
            or not name_ok(name)
        ):
            if name:
                dropped.append(name)
            continue
        if name not in proposals:
            order.append(name)
        proposals.setdefault(name, []).append(person)
    # A shorter name that only ever appears inside a longer proposed name is a fragment.
    order = [
        n for n in order
        if not any(n != o and n in o and text.count(n) == text.count(o) for o in order)
    ]
    rows_order = order[:MAX_ROWS]

    claims: dict[str, set[str]] = {}
    for name in order:
        for person in proposals[name]:
            for alias in (person.get("aliases") or [])[:6]:
                token = str(alias or "").strip()
                if token in FOLDABLE and token not in GENERIC_SOCIAL and token in text:
                    claims.setdefault(token, set()).add(name)
    aliases = {a: n for a, n in rules_alias_map(text, rows_order).items() if n in rows_order}
    for alias, owners in claims.items():
        if alias not in aliases and len(owners) == 1:
            aliases[alias] = next(iter(owners))

    grounder = _Grounder(text, rows_order, narrator, aliases)
    rows: list[dict[str, Any]] = []
    role_tokens = tuple(_ROLE_WORDS | _KIN)
    for name in rows_order[:MAX_ROWS]:
        # (lacks role word, from aliases, evidence window misses raw, length, text)
        candidates: list[tuple[bool, bool, bool, int, str]] = []
        for person in proposals.get(name, []):
            at = person.get("_window", -1)
            window = stage_a.windows[at] if isinstance(at, int) and 0 <= at < len(stage_a.windows) else ""
            raws = [(str(person.get("identity") or "").strip(), False)]
            raws += [
                (str(alias or "").strip(), True)
                for alias in (person.get("aliases") or [])[:6]
                if any(token in str(alias or "") for token in role_tokens)
            ]
            for raw, from_alias in raws:
                grounded = grounder.identity(raw, name) if raw else ""
                if grounded:
                    has_role = any(token in grounded for token in role_tokens)
                    in_window = raw in window and name in window
                    candidates.append((not has_role, from_alias, not in_window, len(grounded), grounded))
        identity = min(candidates)[4] if candidates else ""
        event = ""
        for person in proposals.get(name, []):
            event = grounder.event(person.get("one_event") or "", name)
            if event:
                break
        rows.append({
            "name": name,
            "identity": identity,
            "one_event": event or None,
            "present": any(bool(p.get("present")) for p in proposals.get(name, [])),
        })
    return {"rows": rows, "aliases": aliases, "dropped": dropped}

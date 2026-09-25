"""Character Card V2–compatible and narrative state schemas."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


SOURCE_USER_DECLARED = "user_declared"
SOURCE_MODEL_GENERATED = "model_generated"
SOURCE_INFERRED = "inferred"
SOURCE_TYPES = {SOURCE_USER_DECLARED, SOURCE_MODEL_GENERATED, SOURCE_INFERRED}

LORE_SCOPES = {"character", "user", "chat", "global"}


@dataclass
class CharacterCardV2:
    """Subset of Character Card V2 with unknown-field passthrough."""

    name: str = ""
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_mes: str = ""
    mes_example: str = ""
    alternate_greetings: list[str] = field(default_factory=list)
    character_book: dict[str, Any] | None = None
    creator_notes: str = ""
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "CharacterCardV2":
        data = dict(raw or {})
        known = {
            "name",
            "description",
            "personality",
            "scenario",
            "first_mes",
            "mes_example",
            "alternate_greetings",
            "character_book",
            "creator_notes",
            "extensions",
        }
        extras = {k: v for k, v in data.items() if k not in known}
        extensions = dict(data.get("extensions") or {})
        if extras:
            extensions.setdefault("unknown_fields", {}).update(extras)
        greetings = data.get("alternate_greetings") or []
        if not isinstance(greetings, list):
            greetings = [str(greetings)]
        return cls(
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            personality=str(data.get("personality") or ""),
            scenario=str(data.get("scenario") or ""),
            first_mes=str(data.get("first_mes") or ""),
            mes_example=str(data.get("mes_example") or ""),
            alternate_greetings=[str(g) for g in greetings],
            character_book=data.get("character_book") if isinstance(data.get("character_book"), dict) else None,
            creator_notes=str(data.get("creator_notes") or ""),
            extensions=extensions,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LorebookEntry:
    uid: str
    keys: list[str]
    content: str
    enabled: bool = True
    priority: int = 0
    scope: str = "chat"
    constant: bool = False
    source_offset: int | None = None

    def matches(self, text: str) -> bool:
        if not self.enabled:
            return False
        if self.constant:
            return True
        hay = text.lower()
        return any(k and k.lower() in hay for k in self.keys)


@dataclass
class Lorebook:
    name: str = "default"
    scope: str = "chat"
    entries: list[LorebookEntry] = field(default_factory=list)

    def triggered(self, text: str, *, limit: int = 8) -> list[LorebookEntry]:
        hits = [e for e in self.entries if e.matches(text)]
        hits.sort(key=lambda e: (-int(e.priority), e.uid))
        return hits[: max(0, limit)]


@dataclass
class MemoryRecord:
    fact: str
    scope: str
    source_type: str
    source_offset: int | None = None
    source_document: str | None = None
    confidence: float = 1.0
    valid_from: int | None = None
    superseded_by: str | None = None
    version: int = 1
    canonical: bool = False
    record_id: str | None = None

    def __post_init__(self) -> None:
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"invalid source_type: {self.source_type}")
        if self.canonical and self.source_type != SOURCE_USER_DECLARED:
            raise ValueError("model/inferred facts cannot become canonical without user confirmation")


@dataclass
class SceneState:
    time_place: str = ""
    present_characters: list[str] = field(default_factory=list)
    knowledge: dict[str, list[str]] = field(default_factory=dict)
    relations: dict[str, str] = field(default_factory=dict)
    open_events: list[str] = field(default_factory=list)
    user_choice: str = ""
    scene_goal: str = ""
    forbidden: list[str] = field(default_factory=list)
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "SceneState":
        data = dict(raw or {})
        return cls(
            time_place=str(data.get("time_place") or ""),
            present_characters=[str(x) for x in (data.get("present_characters") or [])],
            knowledge={str(k): [str(v) for v in vals] for k, vals in (data.get("knowledge") or {}).items()},
            relations={str(k): str(v) for k, v in (data.get("relations") or {}).items()},
            open_events=[str(x) for x in (data.get("open_events") or [])],
            user_choice=str(data.get("user_choice") or ""),
            scene_goal=str(data.get("scene_goal") or ""),
            forbidden=[str(x) for x in (data.get("forbidden") or [])],
            version=int(data.get("version") or 1),
        )


@dataclass
class StoryBible:
    persona: str = ""
    characters: list[CharacterCardV2] = field(default_factory=list)
    world_rules: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    style: str = ""
    pov: str = "third_limited"
    user_agency: str = "user_controls_own_actions"
    boundaries: list[str] = field(default_factory=list)
    adults_only: bool = True
    mode: str = "narrative"
    lorebooks: list[Lorebook] = field(default_factory=list)
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona": self.persona,
            "characters": [c.to_dict() for c in self.characters],
            "world_rules": list(self.world_rules),
            "relations": list(self.relations),
            "style": self.style,
            "pov": self.pov,
            "user_agency": self.user_agency,
            "boundaries": list(self.boundaries),
            "adults_only": self.adults_only,
            "mode": self.mode,
            "lorebooks": [
                {
                    "name": lb.name,
                    "scope": lb.scope,
                    "entries": [asdict(e) for e in lb.entries],
                }
                for lb in self.lorebooks
            ],
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "StoryBible":
        data = dict(raw or {})
        characters = [CharacterCardV2.from_dict(c) for c in (data.get("characters") or [])]
        lorebooks: list[Lorebook] = []
        for lb in data.get("lorebooks") or []:
            entries = [
                LorebookEntry(
                    uid=str(e.get("uid") or ""),
                    keys=[str(k) for k in (e.get("keys") or [])],
                    content=str(e.get("content") or ""),
                    enabled=bool(e.get("enabled", True)),
                    priority=int(e.get("priority") or 0),
                    scope=str(e.get("scope") or "chat"),
                    constant=bool(e.get("constant", False)),
                    source_offset=e.get("source_offset"),
                )
                for e in (lb.get("entries") or [])
            ]
            lorebooks.append(
                Lorebook(
                    name=str(lb.get("name") or "default"),
                    scope=str(lb.get("scope") or "chat"),
                    entries=entries,
                )
            )
        return cls(
            persona=str(data.get("persona") or ""),
            characters=characters,
            world_rules=[str(x) for x in (data.get("world_rules") or [])],
            relations=[str(x) for x in (data.get("relations") or [])],
            style=str(data.get("style") or ""),
            pov=str(data.get("pov") or "third_limited"),
            user_agency=str(data.get("user_agency") or "user_controls_own_actions"),
            boundaries=[str(x) for x in (data.get("boundaries") or [])],
            adults_only=bool(data.get("adults_only", True)),
            mode=str(data.get("mode") or "narrative"),
            lorebooks=lorebooks,
            version=int(data.get("version") or 1),
        )

    def config_hash(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class Beat:
    beat_id: str
    goal: str
    target_chars: int
    ordinal: int


@dataclass
class OutlinePlan:
    version: int
    beats: list[Beat]
    target_visible_chars: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "target_visible_chars": self.target_visible_chars,
            "beats": [asdict(b) for b in self.beats],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "OutlinePlan":
        data = dict(raw or {})
        beats = [
            Beat(
                beat_id=str(b.get("beat_id") or f"beat-{i}"),
                goal=str(b.get("goal") or ""),
                target_chars=int(b.get("target_chars") or 0),
                ordinal=int(b.get("ordinal") or i),
            )
            for i, b in enumerate(data.get("beats") or [])
        ]
        return cls(
            version=int(data.get("version") or 1),
            beats=beats,
            target_visible_chars=int(data.get("target_visible_chars") or 0),
        )


def build_outline(
    *,
    target_visible_chars: int = 20000,
    segment_chars: int = 2500,
    topic: str = "",
) -> OutlinePlan:
    from app.services.narrative_chars import segment_char_budget

    budgets = segment_char_budget(target_visible_chars, segment_chars=segment_chars)
    beats: list[Beat] = []
    for i, budget in enumerate(budgets):
        phase = "开端" if i == 0 else ("收束" if i == len(budgets) - 1 else "推进")
        goal = f"{phase}：围绕「{topic or '故事'}」完成本段叙事目标，约 {budget} 可见字符，不要结束整篇。"
        beats.append(Beat(beat_id=f"beat-{i+1:03d}", goal=goal, target_chars=budget, ordinal=i))
    return OutlinePlan(version=1, beats=beats, target_visible_chars=target_visible_chars)


def extract_story_bible_from_text(text: str) -> StoryBible:
    """Deterministic lightweight extraction; preserves full source via offsets later."""
    characters: list[CharacterCardV2] = []
    world_rules: list[str] = []
    relations: list[str] = []
    boundaries: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("角色") or s.startswith("人物") or s.startswith("姓名"):
            name = s.split("：", 1)[-1].split(":", 1)[-1].strip() or s
            characters.append(CharacterCardV2(name=name[:64], description=s))
        elif "关系" in s[:8]:
            relations.append(s)
        elif any(k in s for k in ("禁止", "边界", "不要替", "不代替")):
            boundaries.append(s)
        elif any(k in s for k in ("世界", "设定", "规则")):
            world_rules.append(s)
    if not characters and text.strip():
        characters.append(CharacterCardV2(name="主角", description=text[:500]))
    if not boundaries:
        boundaries.append("不替用户做决定或代写用户动作")
    return StoryBible(
        persona="",
        characters=characters,
        world_rules=world_rules,
        relations=relations,
        boundaries=boundaries,
        adults_only=True,
        mode="narrative",
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

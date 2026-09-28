# Kiln Narrative Context

Kiln separates what the user wants the assistant to play now from facts supplied for later reference.

## Language

**Current scene**:
The setting and cast for the next generation turn. A past or imagined event is not a current scene merely because it appears in the same document.

**Assistant persona**:
The role the assistant should play in the current scene. It is distinct from every person mentioned in reference material.

**User avatar**:
The user's declared identity within a preset's current scene. A later first-person quotation in reference material does not replace it.

**Reference person**:
A person described in the document whose identity can be stored without putting them in the current cast.

**Event ledger**:
Source-grounded past or imagined occurrences, ordered by their appearance in the document. Text order does not imply an absolute chronology across people.

**Preference bank**:
Explicit user preferences that may guide style or interaction. Its entries are not world events and are not literal dialogue to repeat.

**Context IR**:
The typed, editable representation of document segments, persona, avatar, people, relations, events, and preferences before any generation prompt is assembled. It stays server-side. The Studio public draft only shows current scene, me, characters, and binder-attached events — never segment types, spans, or review badges.

**Event binder**:
Closed-set decision that attaches each harvested event to known character names (every co-actor in the evidence clip, up to four), merges consecutive beats only when the who-set is equal, and drops orphans (and under-18 + sexual clips) instead of asking the user to resolve them.

**Attention layers**:
Packed prompt layers for a generation turn. L0 is the short live parlor lock (role, avatar, current scene). L1 is asked-only background. L2 is at most one short preference hint plus named recall events. L3 is never packed (raw source, document meta, off-stage cast).

**Alias**:
A pronoun, kinship word, or role noun (他 / 她 / 姐姐 / 妈妈 / 宝宝 / 闺蜜 / 老师 / 队长 / 校医 / 顾客 / 技师 …) that refers to a person without naming them. An alias is never a character name. Explicit apposition (姐姐陆遥 / 姐姐是陆遥 / 陆遥是我姐姐) folds it onto the proper name by rules; an alias claimed by two names folds onto neither. A folded alias mention counts as event evidence for the named person.

**Alias resolve**:
One closed-set 9B pass on 「解析并预览」 for pastes of 800 characters or more. Input is the live lock, the harvested candidate names, and short alias clips — not the whole document. Output names must appear verbatim in the source; aliases never become rows. The same call returns a short identity per name, kept only when it is grounded near that name's own mentions.

## Time budget

- Chat send: unchanged, milliseconds, no 9B.
- Short paste under 800 characters, 「解析并预览」: rules only, under 2 s.
- Long paste of 800 characters or more, 「解析并预览」: alias resolve with identities (45 s cap). The older clipped fill runs only if its full 50 s budget still fits under the cap, which in practice means only when the resolve made no model call. 20–45 s typical, 60 s hard cap.
- 9B error or timeout: rules harvest minus the alias blocklist, with rules alias folds. The preview still returns.

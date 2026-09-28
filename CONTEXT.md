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

**People extract**:
「解析并预览」 on pastes of 800 characters or more. The 9B goes first: a fixed compiler system prompt, and a user message with the live lock (≤200 chars) plus the reference body in 1200–1800-char windows with 200 chars of overlap, covering the whole reference. It returns people[] JSON only. Rules go second and never propose people ahead of the model: a name must appear verbatim in the source and must not be an alias; an identity or event survives only where the source attaches it to that exact name (the clause holding the name, or a pronoun clause right after it; kinship only by apposition such as 姐姐陆遥 or 林栀是她妹妹). An identity the source gives to the person next door is dropped, not copied. The only rules addition is a last-chance proper name on X是… / X，N岁 / 叫X. Preview returns once, after both passes.

**Alias resolve** (V17, retired from the preview path):
The earlier closed-set pass that captioned 36- and 30-char clips around rules-harvested names. Long-paste preview no longer calls it.

## Time budget

- Chat send: unchanged, milliseconds, no 9B.
- Short paste under 800 characters, 「解析并预览」: rules only, under 2 s.
- Long paste of 800 characters or more, 「解析并预览」: people extract. Windows run concurrently because mlx-lm batches them; about 55 s for a 2.5k diary on the local 9B, 30–70 s typical, 90 s hard cap (75 s per window). The public nginx `/context` route uses the default 60 s read timeout, so a paste that needs more than 60 s only completes on the local origin.
- 9B error, Hub error, or timeout on every window: rules harvest minus the alias blocklist, with rules alias folds, returned immediately with a note. The preview still returns and does not claim the model ran.

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

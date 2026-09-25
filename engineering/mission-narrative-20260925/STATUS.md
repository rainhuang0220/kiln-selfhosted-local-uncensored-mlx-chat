# Narrative Engine Mission — Acceptance Status

## Mission ask (short)

Ship Kiln long-form narrative: diagnose ~2.4K truncation, multi-segment ≥20K visible Chinese chars in one assistant message, story bible / scene / lore structure, Stop/Continue/resume integrity, no regression on interactive chat.

## Round 2 delta (2026-09-26)

### What changed
- `POST /narrative/continue` — idempotent resume from persisted `task_id` + assistant message + segment checkpoint; `narrative_continue_requests` table (migration **0006**).
- Interrupt kinds distinguished: `user_stop`, `network_disconnect`, `resource_pause`, `save_failed` / model failure.
- Resource monitor `narrative_resources.py`: pause next-segment scheduling on **low free swap** or **low Pages free**; **does not** use cumulative Swapouts; **does not** kill MLX.
- `NarrativeOrchestrator.run()` and `continue_job()` both honor resource pause and persist `paused_resource`.
- Atomic committed-segments-only body; unsaved mid-write chars do not count toward stats.
- R4 CPU scorer: `eval/score_r4.py` + exported raw body.

### Files
- `backend/app/services/narrative.py`, `narrative_resources.py`, `narrative_store.py`
- `backend/app/db.py` (0006), `backend/app/main.py` (`/narrative/continue`)
- `backend/tests/test_narrative_continue.py` (12 tests)
- `engineering/mission-narrative-20260925/eval/score_r4.py`
- Evidence under `engineering/mission-narrative-20260925/evidence/`

## Acceptance matrix

| Gate | Result | Evidence |
|---|---|---|
| **R0** 2.4K root cause | **PASS** | Interactive `max_tokens=1536` (unchanged). MLX `--max-tokens 32768` not the limiter. |
| **R1** interactive / route regression | **PASS** | `pytest tests/test_api.py tests/test_narrative_* tests/test_profiles.py` → **49 passed** (2026-09-26). Interactive default still 1536. |
| **R2** structured config | **PASS (API)** | Unchanged from R0–R3 wave. |
| **R3** ≥20K single assistant message | **PASS** | Job `9f12425c-…`: **20637 visible** / **18148 Han** / 23 segs / 1 assistant msg. Body=segments SHA match. See `evidence/live_narrative_20k_body_meta.json`. |
| **R4** 20K semantic quality suite | **FAIL (input_length)** / **PASS (source facts)** / **PASS (heuristic story)** | Frozen `semantic-20k.txt`: raw **20000**, visible **19519** (&lt;20K → **FAIL**), Han **11714**. Fact probes on source: **15/15 PASS**. Live narrative body heuristic story_quality: **PASS** (repeat 0.131, 0 hard failures) — lexical only, **not** subjective quality, and **not** a semantic-20k→answer generation. Answer-side fact retrieval: **not scored** (GPU eval paused under memory pressure). Raw output: `evidence/live_narrative_20k_body.txt`. Scores: `evidence/r4_scores.json`. |
| **R5** resource recovery | **PASS (code+tests)** / live GPU paused | ~18K abort was **client** abort on cumulative Swapouts policy while free swap still healthy. Monitor now pauses on free swap / pages only. Tests: repeat continue, dual client busy, process-restart sim, SSE disconnect, save-failure. API restart applied 0006; **MLX PID 1581 unchanged**. Live pages_free low → GPU eval paused. `evidence/r5_abort_analysis.json`. |
| **R6** production `/chat` path | **PASS** | long_form routing intact; interactive config untouched. |
| **R7** backup / rollback / auth | **PASS** | Backup `kiln-backups/narrative-mission-r5-20260926-024013/`; integrity_check ok; API-only restart; bearer auth. |
| **R8** signed-in browser acceptance | **EXTERNAL DEPENDENCY** | No legitimate browser login session available (browser tabs empty; anonymous `/auth/status` → `ok:false`). Bearer token proves API owner session only — **not** a UI click-path. Do not invent/scrape passwords. |

## Commands / results (Round 2)

```text
# Continue + R5 unit tests
cd kiln/backend && ../.venv/bin/python -m pytest tests/test_narrative_continue.py -v
# → 12 passed

# Broader regression
../.venv/bin/python -m pytest tests/test_narrative_continue.py tests/test_narrative_engine.py \
  tests/test_narrative_chars.py tests/test_api.py tests/test_profiles.py -q
# → 49 passed

# Deploy (API only — MLX untouched)
# backup → launchctl kickstart -k gui/$UID/com.kiln.api
# MLX before/after PID: 1581 / 1581
# schema_migrations includes 0006_narrative_continue

# Live continue on completed job (idempotent / already_complete)
POST /narrative/continue job=9f12425c… idempotency_key=live-complete-probe-1
# body length stayed 21001; second call same key → replay; no truncation/dupe

# R4 CPU score
.venv/bin/python engineering/mission-narrative-20260925/eval/score_r4.py
# input_length FAIL (19519 visible); fact_retrieval PASS; story_quality heuristic PASS
```

## DB verification

```text
sqlite3 kiln/data/chat.db "SELECT version,name FROM schema_migrations ORDER BY version;"
# … 5|0005_narrative_engine
# … 6|0006_narrative_continue

sqlite3 kiln/data/chat.db "PRAGMA table_info(narrative_jobs);" | egrep 'pause_reason|interrupt_kind'
sqlite3 kiln/data/chat.db "SELECT name FROM sqlite_master WHERE name LIKE 'narrative%';"
# narrative_continue_requests present

sqlite3 kiln/data/chat.db \
  "SELECT length(content) FROM messages WHERE id=(SELECT assistant_message_id FROM narrative_jobs WHERE job_id='9f12425c-98af-4942-9b53-1a9a7780263c');"
# 21001 (unchanged after continue probes)
```

## Rollback

1. **API code**: restore prior tree / `launchctl kickstart -k gui/$UID/com.kiln.api` from last known-good.
2. **DB**: copy back `kiln-backups/narrative-mission-r5-20260926-024013/chat.db` (+ wal/shm if needed); or prior `narrative-mission-*` backups.
3. **MLX**: do nothing (never restarted this wave; PID 1581).
4. **Schema**: 0006 is additive (`pause_reason`, `interrupt_kind`, `narrative_continue_requests`); dropping the continue table is safe if rolling back code that references it.

## Still failing / next concrete steps

1. **R4 input_length**: frozen `semantic-20k.txt` is 20000 raw / **19519 visible** — gate stays **FAIL** until a new frozen fixture is explicitly ≥20000 **visible** (do not silently rewrite without a freeze decision).
2. **R4 answer fact retrieval / full long-form quality vs semantic ledger**: blocked on GPU while `pages_free` is low (`should_pause` true). Next: wait for free pages/swap recovery, then **serial** GPU eval of semantic-20k → long_form output → answer probes.
3. **R8**: owner must log into the public/local UI with a real password; then re-run browser Stop/Continue acceptance. No password bypass.

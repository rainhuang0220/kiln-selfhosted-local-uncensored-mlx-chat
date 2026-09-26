# release_acceptance_report.md

**Decision: READY WITH LIMITATIONS**

Date: 2026-09-26 (Asia/Shanghai). Public: https://kiln.plainlist.space. Tag: `v0.1.0-beta` (`7061166`). MLX PID **1581** @ **127.0.0.1:8081**.

## Authentication

| Check | Result | Evidence |
| --- | --- | --- |
| Tunnel restored (API reachable) | PASS | public `/auth/status` 200 after tunnel kickstart |
| Account acquisition documented in product | PASS | AuthGate copy + `create-user` CLI; asset `index-Bst4Wrrq.js` |
| Login (QA user) | PASS | `…/phase1_auth_acceptance.json` `phase1_pass: true` |
| Session survives refresh | PASS | same (`ok:true`, username `qa_release`) |
| Wrong password clear error | PASS | 401 `auth_failed` / “invalid username or password” |
| Anonymous cannot chat | PASS | 401 `auth_required` |
| API error hygiene | PASS | structured error codes; no stack traces in auth responses |

Root cause of prior inability to enter: (1) **P0 tunnel 502**, fixed; (2) **private owner-issued accounts** (not open signup), documented + CLI issue path.

## Deployment

| Check | Result |
| --- | --- |
| Public homepage HTTPS | PASS |
| Static Long Form + auth copy deployed | PASS |
| `/narrative` proxied | PASS (401 unauth) |
| MLX not public | PASS (`127.0.0.1:8081` only) |
| DB backup present | PASS (`narrative-mission-r5-20260926-024013`) |

## Runtime

| Check | Result |
| --- | --- |
| Local `/health` | PASS |
| Authed short chat via public | PASS (`pong`, HTTP 200) |
| Tunnel reliability | LIMITATION — can drop; recover via web-tunnel kickstart |

## Long context

| Check | Result |
| --- | --- |
| Scenario 1 (20-turn chat) | **not started** — Phase 2 paused |
| Scenario 2 (persona 30-turn) | **not started** |
| Reason | `should_pause_for_resources` → `low_pages_free` (pages_free≈1398) |

## Narrative

| Check | Result |
| --- | --- |
| Prior live ≥20K visible (engineering) | PASS historically (20637 visible / 18148 Han) |
| Scenario 3 (5k/10k/20k quality) | **not started** this wave (GPU paused) |
| Scenario 4 Stop/Refresh/Continue | **not started** this wave |

## Known limitations

1. **KNOWN LIMIT** — Phase 2 model/persona/narrative acceptance not run under low pages free; do not kill MLX to free memory.
2. **KNOWN LIMIT** — R4 GPU 10–15Q incomplete (prior).
3. **KNOWN LIMIT** — Uncensored SKU safety boundaries.
4. **KNOWN LIMIT** — Public `/health` nginx 404 by design.
5. Open self-signup remains **disabled** (intentional for private uncensored exposure).

## Problem classes observed this wave (Phase 3)

| Issue | Class |
| --- | --- |
| Public auth 502 / tunnel loss | **E product engineering** (ops / reverse SSH reliability) |
| Visitors cannot self-register | **E product engineering** (private-mode policy; documented) |
| AuthGate lacked account-acquisition copy | **E product engineering** (fixed minimally) |
| No second-user CLI before this wave | **E product engineering** (added `create-user`) |
| Phase 2 blocked by RAM pressure | **E product engineering** / ops (host memory), not model weights |

No class **A** model-limitation claims were used to change the model.

## Research plan only (Phase 4 — do not implement)

Prior note: `engineering/2026-09-24/agents/A8-prompt-compression.md` (LLMLingua not installed; prefer exact context → chunk retrieval with offsets → lossy compress only with regression gates).

If Phase 2 later shows:

| Class | Prefer researching (not implementing now) |
| --- | --- |
| B prompt / persona drift | Character Card V2 + Lorebook; keep creator_notes out of stable runtime |
| C context engineering | Hierarchical Story Bible summaries; RAG over archived turns with offsets (align with A8) |
| D memory architecture | Mem0 / LangMem / LongMemEval-style eval harness before MemGPT-style tools |
| Length vs quality | Do not chase visible-char targets as quality; score continuity axes separately |

Do **not** re-download LLMLingua models or run live generation for this research note.

## Decision rationale

**READY WITH LIMITATIONS** — a real issued user can obtain an account (CLI), log in on the public site, keep a session, see clear auth errors, and call chat while anonymous users cannot. Full multi-turn / narrative QA is deferred until host memory recovers, without touching MLX.

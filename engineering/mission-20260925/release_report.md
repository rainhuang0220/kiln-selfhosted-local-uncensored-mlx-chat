# Kiln release report — RC 2026-09-25

Labels used only: **PASS**, **PARTIAL**, **KNOWN LIMIT**.

## Deployment

| Field | Value |
| --- | --- |
| Branch | `eng/inference-baseline-20260924` |
| Commit | _d7d5520_ |
| API | PID **8283**, `127.0.0.1:8787` |
| MLX | PID **1581**, `127.0.0.1:8081` (not restarted) |
| Web | PID 97771, `127.0.0.1:7777` |
| Pushed | false |

### Rollback (API only; do not touch MLX)

1. `git switch --detach <previous-sha>`
2. `launchctl kickstart -k gui/$(id -u)/com.kiln.api`
3. Return: `git switch eng/inference-baseline-20260924` + same kickstart.

DB backup before this RC API restart: `../kiln-backups/2026-09-25/chat-before-context-route-wire.db` (`integrity_check=ok`).

## What changed in this RC

- Wired existing `context_route.route_document` into `/chat` for long user messages; short messages stay verbatim on the original path.
- Extractive compression attempted first; rejection falls back to retrieval (or marked pack if verbatim exceeds budget).
- Snapshot `document_pack.context_route` always carries `archive_sha256`, mode, served/original chars, `silent_truncation=false`.
- `answer_verify`: unit-less questions stay `insufficient_evidence`; labeled subtraction computes in code (e.g. 1462−187→1275卷).
- `ingest` empty-chunk path marks packs (no silent raw prefix).
- Stopped and **disabled** `com.kiln.mtplx-tunnel` (VPS reverse of `:8081`) without restarting MLX.

## Browser / live verification

| Check | Result |
| --- | --- |
| Signed-in browser UI | **External blocker**: private mode requires password; none in repo/`api.env`. UI at `:7777` returns 200 (login gate). |
| Authenticated API short chat | **PASS** — `context_route.mode=verbatim`, `applied=false`, sha256 present (`eval/rc-live-verify.json`) |
| Authenticated API long chat | **PASS** — `mode=retrieval`, `applied=true`, `original_chars=26416` > `served_chars=22472`, `silent_truncation=false` |
| SSE Stop/Continue on current API | **PASS** — abort→one assistant; continue in place; seq monotonic |
| Evidence numeric correction | **PASS** — model `10 卷` corrected to `1275卷` via structured difference |

## Gate outcomes

| Gate | Label | Evidence |
| --- | --- | --- |
| G0 rollback / API-only move | **PASS** | DB backup + API kickstart; MLX PID 1581 unchanged |
| G1 health READY | **PASS** | `/health` → READY / `user_generation` after RC verifies |
| G1 video pause | **KNOWN LIMIT** | Do not bootout production MLX under swap pressure |
| G2 behavior-v2 (28/30) | **PARTIAL** | `eval/behavior-v2-scores.json` |
| G2 V17/V18 safety | **KNOWN LIMIT** | Uncensored Aggressive SKU; `behavior-v2-audit.md` |
| G3 20K semantic missing cases | **PARTIAL** | cross+refusal PASS; raw model numeric was wrong; verifier now computes when `evidence` supplied |
| G4 router latency | **PARTIAL** | Frozen three-path table + live long retrieval route |
| G5 SSE + Stop/Continue | **PASS** | fuzz + `rc-live-verify.json` / `stop-continue-chain.json` |
| G6 disk / no deletions | **PASS** | 30 protect / 0 delete |
| G7 current deploy exercised | **PARTIAL** | API+routing+Stop/Continue verified; signed-in browser blocked |
| G8 standards + security | **PARTIAL** | Independent reviews filed; P1 fixed; tunnel disabled this wave |
| Context route in `/chat` | **PASS** | Unit tests + live short/long (`rc-live-verify.json`) |
| MLX bind localhost only | **PASS** | `lsof` → `127.0.0.1:8081`; tunnel LaunchAgent disabled |
| Public path bypass to raw MLX | **PASS** | Web tunnel remains `:17777`→API only; `:8081` reverse tunnel stopped |

## Storage

All previously protected models **kept** (including Qwen2.5-1.5B, learning/image/video, 27B APFS clones, resident 9B). Zero deletions.

## Remaining risks

1. Signed-in browser RC not run (password external blocker).
2. Video pause still not exercised (KNOWN LIMIT / do-not-bootout).
3. Uncensored model will answer harmful howtos (KNOWN LIMIT V17/V18).
4. Re-enabling `com.kiln.mtplx-tunnel` would again expose raw MLX on VPS loopback — keep it disabled unless compose/Caddy intentionally needs it.

---

# Final Validation Phase — 2026-09-26

Labels used only: **PASS**, **PARTIAL**, **KNOWN LIMIT**, **EXTERNAL BLOCKER**.

## Environment

| Field | Value |
| --- | --- |
| MLX | PID **1581** before and after (unchanged; not restarted) |
| API | `127.0.0.1:8787` (narrative continue + R5 pause already shipped) |
| Rollback DB | `../kiln-backups/narrative-mission-r5-20260926-024013/` |
| Interactive `max_tokens` | unchanged at **1536** |

## Fixture correction (R4 input-length)

| Item | Value |
| --- | --- |
| v1 (historical, unmodified) | `eval/semantic-20k.txt` |
| v1 SHA256 | `10e8768254c1946384d53f263bfb7470894cd6e759f4d9024324dfe03ad93b06` |
| v1 visible / Han / tokens | 19519 / 11714 / 13217 |
| **v2** | `eval/semantic-20k-v2.txt` (+ mirror `../mission-narrative-20260925/eval/semantic-20k-v2.txt`) |
| v2 SHA256 | `b3a1509f7361ec07ba42c16103a9cb1cf9507a4248abc8738d04a29c818b808e` |
| v2 visible / Han / tokenizer tokens | **20227** / **12235** / **13708** |
| Input-length axis (v2 visible ≥ 20000) | **PASS** |
| Meta record | `eval/semantic-20k-v2.meta.json` |

## Gate outcomes (this phase)

| Gate | Label | Evidence |
| --- | --- | --- |
| R0–R3 narrative foundation | **PASS** | Prior mission; not re-run |
| Narrative Engine + `POST /narrative/continue` | **PASS** | Prior wave; 12 continue/R5 tests green |
| R5 resource pause | **PASS** | Free-swap / pages-free monitor; MLX not killed |
| R4 input-length (v2) | **PASS** | visible 20227 ≥ 20000; Han 12235 recorded separately |
| R4 GPU fact/quality eval (10–15 Q) | **KNOWN LIMIT** | Paused before start: `low_pages_free` (pages_free≈4166, free swap≈1002 MiB). No questions executed. Record: `../mission-narrative-20260925/evidence/r4_gpu_eval_v2.json` |
| R8 signed-in browser Stop/Continue/long-form | **EXTERNAL BLOCKER** | No legitimate browser login session; anonymous `/auth/status` → `ok:false`. Bearer ≠ UI acceptance. |

## Rollback pointer

1. DB: restore `../kiln-backups/narrative-mission-r5-20260926-024013/`
2. API only: `launchctl kickstart -k gui/$(id -u)/com.kiln.api`
3. MLX: do nothing (PID 1581 left running)

## Explicit non-actions

- Did not edit `semantic-20k.txt` (v1).
- Did not start GPU eval under memory pressure.
- Did not invent passwords or bypass auth for R8.
- Did not change interactive chat output config or production MLX flags.
- Did not git push / change git identity.

---

# Public Release Phase — 2026-09-26

Labels used only: **PASS**, **PARTIAL**, **KNOWN LIMIT**, **EXTERNAL BLOCKER**.

## Version

| Field | Value |
| --- | --- |
| Version / tag | `v0.1.0-beta` (GitHub Release, prerelease) |
| Branch | `eng/inference-baseline-20260924` |
| Public URL | **https://kiln.plainlist.space** |
| Deploy path reused | Existing VPS nginx + SSH reverse tunnel `VPS:17777 → Mac:8787`; LaunchAgent `com.kiln.web-tunnel`; local API `:8787`; Vite `:7777` (local only) |
| MLX | PID **1581**, bind **127.0.0.1:8081** only — not publicly exposed |
| DB backup | `../kiln-backups/narrative-mission-r5-20260926-024013/` |
| Migrations | through `0006_narrative_continue` |

## Features (this RC)

- Long-form Narrative Engine (`long_form` / `mode=narrative`) with multi-segment generation
- `POST /narrative/continue` with idempotency + checkpoint resume
- Resource pause/resume (free swap / pages free; does not kill MLX)
- Context router on long chat turns (prior RC)
- Evidence / answer verification when evidence is supplied (prior RC)
- Private-mode auth wall on the public hostname

## Real benchmark numbers (evidence, not marketing)

| Metric | Value | Note |
| --- | --- | --- |
| Interactive truncation root cause | `max_tokens=1536` | Not MLX 32K ceiling |
| Live long-form body | **20637 visible chars** / **18148 Han** / 23 segments / 1 assistant message | Job `9f12425c-…`; visible ≠ Han |
| Frozen input v2 | **20227 visible** / **12235 Han** / **13708 tokenizer tokens** | `eval/semantic-20k-v2.txt` |
| Continue / R5 unit tests | **12 passed** | `tests/test_narrative_continue.py` |
| Broader narrative+api+profiles | **49 passed** | pytest wave |

## Completed (actually passed)

| Gate | Label | Evidence |
| --- | --- | --- |
| Public homepage HTTPS | **PASS** | `https://kiln.plainlist.space/` → 200 (`evidence/public-release/unauth_surfaces.txt`) |
| Auth wall (anonymous) | **PASS** | `/auth/status` → `required:true,ok:false`; `/chat` anonymous → **401** |
| MLX not public | **PASS** | `lsof` → `127.0.0.1:8081`; public `:8081` unreachable; `com.kiln.mtplx-tunnel` not loaded |
| API local health | **PASS** | `127.0.0.1:8787/health` → 200 |
| DB backup + migrations | **PASS** | backup dir + schema through 0006 |
| Narrative RC freeze commit | **PASS** | committed for release (no `.env` / tokens) |

## Partial

| Gate | Label | Evidence |
| --- | --- | --- |
| Public `/health` path | **PARTIAL** | nginx returns 404 for `/health` on the public hostname; auth and chat routes are proxied and enforce 401. Local `/health` is 200. |

## Known Limitations (unhidden)

| Gate | Label | Detail |
| --- | --- | --- |
| Signed-in browser acceptance (login, short/long chat, narrative stop/continue/refresh, SSE UI) | **EXTERNAL BLOCKER** | No legitimate browser login session in this agent. Password not invented. Developer must log in at the public URL to accept. |
| R4 GPU 10–15Q benchmark | **KNOWN LIMIT** | Incomplete — paused on `low_pages_free`. |
| Safety boundary cases (uncensored SKU) | **KNOWN LIMIT** | Prior behavior-v2 V17/V18; model may answer harmful howtos. |
| Inference capability | **KNOWN LIMIT** | Gateway may report `UNVERIFIED` until a fresh verified probe. |

## Human step remaining

1. Open **https://kiln.plainlist.space**
2. Log in with the existing owner account (password not in repo)
3. Accept: short chat, long chat, Long Form generate → Stop → refresh → Continue

## Security checklist

- MLX listen: **127.0.0.1:8081** only (PID 1581)
- API auth required when `KILN_EXPOSURE=private`
- CORS via `allowed_origins` + public origin
- Secrets offline: `~/Library/Application Support/kiln/api.env`, tunnel key, mission token — **not** in git
- Rate limit path present in `backend/app/auth.py`
- Rollback: DB backup above; API-only kickstart; never restart MLX for rollback of this wave


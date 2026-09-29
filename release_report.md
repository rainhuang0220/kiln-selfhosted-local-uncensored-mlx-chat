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

# G8 standards / product-spec review — inference baseline

**Reviewer role:** independent standards/spec pass (did not author the reviewed diffs).  
**Branch:** `eng/inference-baseline-20260924`  
**API behavior pin:** `7a710f2` (HEAD may be ledger-only `9aca60c` / `8571a4b`; backend service files under review match `7a710f2` for the focus modules).  
**Method:** static read of source, unit-test files, and mission ledger claims.  
**Explicit:** this review did **not** call the live model, did **not** hit MLX `:8081`, and did **not** run generation.

---

## Verdict

**PARTIAL** for the G8 *standards / product-spec* aspect of the deployed inference baseline.

The ledger correctly still labels gate **G8 = FAIL** for a full independent recheck of every live gate. This document is only a focused standards/spec audit of the five areas below. Several contracts are implemented and test-backed; one real evidence-correction over-apply bug and the unused `context_route` production path keep the standards aspect from PASS.

---

## Findings

### P0

None confirmed in the five focus areas by static review alone.  
(G2/G3 live quality failures in `acceptance.json` remain open product gates, but they are outside “invented” code bugs in these modules.)

### P1

1. **`answer_verify.verify_answer` over-applies “last number in evidence” when the question does not name a unit or a compare-pair** — **real bug** (product intent: named measurement only).  
   - **Where:** `backend/app/services/answer_verify.py:162-165` (then applied by `backend/app/services/chat.py:1473-1480`).  
   - **Evidence:** with `question="合同编号是多少"`, `evidence="这里没有合同编号。附件有3页。"`, `model_output="不知道"`, the function returns `VerifiedAnswer(answer='3', source='evidence', model_number_ok=False, ...)`. Chat would replace the model text.  
   - **Contrast:** commit / convergence text say ordinary chats and unnamed measurements leave the model text alone; the no-digit case is tested (`test_api.py` “这里没有合同编号”), the incidental-digit case is not.  
   - **Smallest fix:** refuse (`insufficient_evidence`) unless a unit is present in the question, a label-pair difference path succeeds, or a verbatim-quote path applies—do not take `values[-1]` for unit-less free questions.

2. **`context_route.route_document` is not on the deployed chat path** — **documentation / architecture gap** (with product impact on G3/G4 claims that imply a routed archive).  
   - **Where:** no import/call from `backend/app/services/chat.py`; production packing is `ingest.pack_user_message` at `chat.py:621`. Already noted in `engineering/mission-20260925/takeover-baseline.md` (~line 26–27).  
   - **Impact:** isolated guarantees (immutable archive hash, `silent_truncation=False`, compression→retrieval fallback) hold for the *library* and its tests, not for what PID-loaded `7a710f2` does on `/chat`.  
   - **Smallest fix:** either wire `route_document` into packing with citations surfaced on the snapshot, or stop treating `context_route` results as deployed-baseline acceptance evidence (keep pack-path claims only).

### P2

3. **SSE `snapshot` payload reuses `request_id` for the DB snapshot id, then `main.event_stream` overwrites it with the stream UUID** — **documentation / naming gap** (not a seq-order bug).  
   - **Where:** `chat.py:1314` sets `"request_id": snapshot_id`; `main.py:748-754` always assigns a new per-stream `request_id` + monotonic `seq`.  
   - **Effect:** frame ordering/correlation works; the context-snapshot UUID is not present on the live SSE `snapshot` event under that key. Reload path uses `/conversation/{id}/context` (`chat-store.ts`) instead.

4. **`ingest.pack_document` empty-chunk fallback is a raw prefix cut** — **edge-case real bug** (rare).  
   - **Where:** `backend/app/services/ingest.py:117-118` (`text[: max(1, budget * 2)]` with `applied=True` but no `[... omitted ...]` / `<document packed>` wrapper).  
   - Normal multi-chunk packs are explicitly marked (`ingest.py:135-142`), so they are not silent. Whitespace-only / empty-chunk path is the exception.

5. **Gateway `state` collapses `FAILED` → `DEGRADED` while `inference_capability` stays `FAILED`** — **by design / documentation**, not a bug.  
   - **Where:** `gateway.py:36-37`. Matches `engineering/2026-09-25/readiness.md`. Callers must read `inference_capability`, not only `gateway.state`.

---

## Spec compliance checklist

| Claim | Result | Evidence |
| --- | --- | --- |
| Evidence checks run only when the request supplies `evidence` | **yes** | `main.py:69`, `main.py:739`; `chat.py:1457`; ordinary chat test omits `answer_check` (`test_api.py` ~172–186) |
| Corrections are evidence-derived (numbers/units/quotes), not free invention | **partial** | Module docstring + difference/quote paths (`answer_verify.py:125-181`); **fails** on incidental last-number (Finding P1.1) |
| Original model text kept beside correction | **yes** | `chat.py:1463-1466`, `_finalize_assistant` metadata (`7a710f2`); `test_api.py:226-250` |
| `insufficient_evidence` leaves model text unchanged | **yes** (when that source is returned) | `chat.py:1468-1477`; `test_api.py:237-241` |
| `context_route`: no silent truncation flag | **yes** (module) | All `RouteResult` paths set `silent_truncation=False` (`context_route.py:141,153,185,211`); tests assert it |
| `context_route`: archive sha256 preserved across modes / fallback | **yes** (module) | `_archive` (`context_route.py:59-61`); compression/fallback tests in `test_context_route.py` |
| `context_route`: rejected compression falls back to retrieval | **yes** (module) | `context_route.py:160-217`; tests for empty/unchanged/over_budget/missing facts/exception |
| Deployed `/chat` uses `context_route` for long docs | **no** | `chat.py` uses `pack_user_message` only; `takeover-baseline.md` |
| Production oversize pack is marked (not silent) when chunks exist | **yes** | `ingest.py:135-142`; UI surfaces `document_pack` (`app.tsx`) |
| Full-document request refuses pack-down | **yes** | `chat.py:622-623` raises when `full_document and packed.applied` |
| Capability states `UNVERIFIED` / `READY` / `BUSY` / `DEGRADED` / `FAILED` | **yes** | `inference_watch.py:67-76`; `/health` exposes them (`main.py:335-368`); unit tests under `test_inference_*.py`, `test_readiness_probe.py` |
| `/health` does not generate | **yes** | `gateway.py` / `readiness.md`; probe is separate (`readiness_probe.py`) |
| SSE frames share one `request_id` and monotonic `seq` from 1 | **yes** (API) | `main.py:745-754`; `test_api.py:287-311` |
| Client rejects duplicate / gap / foreign `request_id` | **yes** (web tests; not live browser log) | `sse-assembly.ts`; `sse-fuzz.test.ts`; acceptance G5 already PARTIAL on live frame log |
| `acceptance.json` claims match code for evidence + readiness wiring | **yes** (honest PARTIAL/FAIL labels) | Ledger does not claim G8 PASS; convergence evidence-check text matches gated apply rules (except P1.1 hole) |
| `acceptance.json` “no silent truncation” as a completed G3 | **no** (gate still FAIL) | `acceptance.json` G3; not re-proven here; pack ≠ full 20k fidelity |

---

## Focus-area notes

### 1. `answer_verify.py` — evidence-only edits?

**Intent match with a hole.** Verbatim quotes replace with the evidence span; labeled differences compute from evidence numbers; bare unit questions take the last unit-matched number; subtraction-style questions refuse. Chat applies only for reliable sources when the model number is wrong, a unit is restored, or extra context appears on a quote. Original text is persisted (`7a710f2`).

The unit-less “any trailing digit” path (P1.1) is not evidence-*named* editing and can overwrite a correct refusal/unknown with an incidental figure.

### 2. `context_route.py` — no silent truncation, hash, compression fallback?

**Module: yes.** Archive `sha256` is content-addressed; compression failures fall back to ranked chunks with citation offsets into the original text; `silent_truncation` is never set true.

**Deployed baseline chat: N/A / not wired.** Long-prompt behavior is `ingest.pack_*` (marked omissions) plus dialogue fold flags on the snapshot.

### 3. `gateway.py` + readiness/health — capability states?

**yes.** `InferenceWatch.capability` emits the five states; busy forces `BUSY`; TTL expiry returns `UNVERIFIED` not `FAILED`; `/health` maps provider reachability separately from capability. Probe code exists but is flag-gated and is not invoked by `/health`.

### 4. Streaming / SSE `request_id` + `seq`

**API contract: yes.** Every JSON SSE payload from `/chat` stream gets the same UUID `request_id` and increasing `seq` (including heartbeats via `iterate_with_heartbeats` → `stamped`). Trailing `data: [DONE]` is wire-only. Frontend assembly enforces order; on clean `done`, UI prefers `message.content` (so post-stream evidence corrections can replace streamed deltas).

Live browser frame-order logging for PID `64536` / commit `7a710f2` is **not** claimed here (matches acceptance G5 PARTIAL).

### 5. `acceptance.json` vs actual code claims

| Gate label in ledger | Standards judgment on code claims |
| --- | --- |
| G0 PASS | Not re-executed; no contradiction in code review |
| G1 PARTIAL | Code supports UNVERIFIED-after-restart; matches ledger |
| G2 FAIL | Behavior quality; not contradicted by these modules |
| G3 FAIL | `context_route` tests ≠ deployed chat packing; ledger FAIL remains appropriate |
| G4 PARTIAL | Speed-path numbers are ledger/MLX observations, not proven via `chat.py`→`context_route` |
| G5 PARTIAL | SSE API + fuzz tests exist; live seq log still open |
| G6 PASS | Out of scope for this file set |
| G7 PARTIAL | Commit pin `7a710f2` matches reviewed API code |
| G8 FAIL | Still correct for *full* independent gate recheck; this review only covers standards aspect → **PARTIAL** |

No claim of newly passing live tests is made.

---

## Recommended smallest fixes

1. **P1.1:** In `verify_answer`, remove or gate the bare `_numbers(...); values[-1]` success path so unit-less / non-pair / non-verbatim questions return `insufficient_evidence`. Add a regression test with incidental digits (合同编号 + “3页”).  
2. **P1.2:** Decide and document: either integrate `route_document` into `chat` packing, or annotate mission docs / G3–G4 evidence so only `ingest.pack_user_message` counts for the deployed baseline.  
3. **P2.3 (optional):** Put DB snapshot id under `snapshot_id` (or similar) so SSE `request_id` remains solely the stream correlator.

---

## What this review did not do

- Did not call MLX `:8081` or any generation endpoint.  
- Did not restart API/MLX or re-run vitest / pytest.  
- Did not re-score G2 behavior samples or G3 20k items.  
- Did not update `acceptance.json` gate statuses (G8 remains FAIL until a full independent live recheck is recorded).

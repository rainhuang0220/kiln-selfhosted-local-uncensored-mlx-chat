# Convergence report — 2026-09-25 19:42 CST

Verdict: IN PROGRESS. This is not COMPLETE.

HEAD `7a710f2` on `eng/inference-baseline-20260924`, unpushed. MLX stayed PID 1581. API was restarted alone to PID 64536 and is `UNVERIFIED` / `AVAILABLE` / provider reachable. Web was not rebuilt. No model files were downloaded or deleted. MLX flags and the frozen question sets were not changed.

An 8-second idle sample while MLX had no client connection showed Swapouts 76,059,679 → 76,067,959 (+8,280 pages), Pageouts +133, Swapins +414. Swap then stood at 19,456 MiB total, about 18,541 MiB used, about 915 MiB free, and later about 1,127 MiB free. No further generation was sent.

## 1. Evidence check

PASS for the API behavior that has tests. PARTIAL for a signed-in production chat.

`answer_verify.py` runs only when the chat request includes `evidence`. Ordinary chat omits `answer_check`. A correction is applied only for `evidence`, `evidence_difference`, or `evidence_quote`, and only when the model number disagrees, the unit is restored from the evidence, or a verbatim answer added text outside the quote. `insufficient_evidence` leaves the model text unchanged.

The original model text, the reason, and `applied` are stored on the assistant row in `messages.metadata_json` and returned on the done message and on `GET /conversation/{id}`. They are not written into `error`.

`tests/test_api.py` and `tests/test_answer_verify.py` plus `tests/test_context_route.py`: 21 passed. The full `tests/test_api.py` file: 20 passed. SQLite backup `../kiln-backups/2026-09-25/chat-before-answer-check-persist.db` (2,203,648 bytes, `integrity_check=ok`) was taken before the API-only restart.

No signed-in browser request has sent `evidence` to PID 64536.

## 2. G4 three paths

PARTIAL. Source: `speed-paths.md`. Document: `eval/semantic-20k.txt`, 20,000 characters. Question: unpaid id. Gold: 44091. MLX PID 1581, temperature 0, swapout delta 0 on these calls. No TTFT column.

| Path | Prompt tokens | Cached tokens | Seconds | Answer |
| --- | ---: | ---: | ---: | --- |
| Cold full text | 13240 | 0 | 62.754 | 44091 |
| Same prompt again | 13240 | 13236 | 0.588 | 44091 |
| Retrieval, 500 characters | 335 | 0 | 2.477 | 44091 |
| Extractive compression, 2426 characters | 1890 | 0 | 8.856 | 44091 |

Retrieval is about 25× the cold full-text time on this one lookup. Compression is about 7×. CPU compression was under 0.001 second and is not LLMLingua. The cache-reuse row is a separate path.

Failure reasons already on the record: full-text prefill is 62.754 seconds versus the older 65.1 second / 13,476-token baseline, so it is not twice as fast. That 2× full-prefill target is not required for this product conclusion. The three-path table is one question, direct to MLX, with no browser TTFT and no second document. Four other retrieval questions (预算, 外包, 缺页, 函数) were summarized as expected at about 2 seconds and 330 tokens; their outputs were not saved item by item.

On this suitable lookup, the router paths cut end-to-end time while keeping the same answer. That is the accepted product result for this item. It is not a 50-item median and it is not a Kiln-browser measurement.

## 3. G3 on the frozen 20K semantic document

FAIL as a completed quality set. Transport of a different 20,032-token repeated-character prompt is not reused as semantic proof.

| Check | Result | Why |
| --- | --- | --- |
| Key fact, unpaid id 44091 | PARTIAL | Same answer on full, retrieval, and compression. See the table above. |
| Key facts 预算 / 外包 / 缺页 / 函数 | PARTIAL | `speed-paths.md` says each retrieval reply matched the expected value. Per-item outputs, tokens, and latency were not saved. |
| Numeric difference, 1462 volumes minus 187 missing volumes | FAIL | No saved model answer. The document states both figures. 1275 was not graded. |
| Cross-section, opening refusal to outsource versus the closing line that 北窗科技 received no contract | FAIL | No saved model answer that ties the two passages. |
| Refusal when the asked fact is absent | FAIL | No saved model refusal. |

A direct POST to `127.0.0.1:8081` in this same session raised `TimeoutError: timed out` before a body was read. MLX stayed PID 1581. The idle swapout sample above is why those three missing grades were not retried.

The separate 50 short documents remain 28/50 exact, 18 number-without-unit, L14/L16 partial quotes, L24 and L28 numerically wrong. That set is not `semantic-20k.txt`.

## 4. Real path already on record

Do not treat these as a retest of PID 64536.

| Check | Label | Evidence |
| --- | --- | --- |
| Signed-in browser generation | PASS on `cf2dee9` and `53e6eac` | `live-deploy-20260925.md`: KILN-OK, TTFT 2835 ms, health READY by user_generation; POST-DEPLOY-OK, TTFT 2840 ms |
| Stop | PASS on that browser session | Message became “已中断” |
| Continue | PASS on that browser session | Refresh kept 94 output tokens and Continue; one assistant message, 308 characters, TTFT 1648 ms |
| Session save | PASS on that browser session | The continued message persisted across refresh |
| SSE order | PARTIAL | `sse-fuzz.test.ts` covers 1000 cut streams. The browser session did not log frame sequence numbers |
| Video pause and 3-minute recovery | FAIL | Not run. Booting out PID 1581, or starting a second 9B, is unsafe while swapouts are still rising |

## 5. Gate labels

| Gate | Label | Reason |
| --- | --- | --- |
| G0 | PASS | Earlier API rollback drill did not touch MLX. This wave only moved the API forward, to PID 64536. |
| G1 | PARTIAL | Health split and a real READY observation exist. Current process is UNVERIFIED. Video recovery was not run. |
| G2 | FAIL | 30/30 returned text and no refusal opener. B08 timezone and B24 sentence count are real quality failures. |
| G3 | FAIL | The four semantic checks above are not all measured. |
| G4 | PARTIAL | One frozen three-path lookup is faster on retrieval and compression with the same answer. Not an end-to-end median. |
| G5 | PARTIAL | Browser Stop/Continue exists on an older API. Full-text prefill is not 2× and is not being forced. User-visible router TTFT was not measured in Kiln. |
| G6 | PASS | 30 protected paths, zero deletions. |
| G7 | PARTIAL | API PID 64536 is `7a710f2`. Browser and public proof stop at `53e6eac`. |
| G8 | FAIL | No independent recheck of `7a710f2`. |

Rollback of this API wave, without touching MLX: `git switch --detach 88a5e28` and `launchctl kickstart -k gui/$(id -u)/com.kiln.api`. Return with `git switch eng/inference-baseline-20260924` and the same kickstart. Do not push.

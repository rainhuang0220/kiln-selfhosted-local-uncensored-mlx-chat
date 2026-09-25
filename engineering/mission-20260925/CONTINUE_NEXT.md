# CONTINUE_NEXT

Status: IN PROGRESS. Do not mark Kiln COMPLETE. The acceptance ledger is `acceptance.json`.

Production baseline: MLX PID 1581 on 8081, API PID 70476 on 8787, public web asset `index-CJGbwbMg.js` from `a672a2f`. MLX has not been restarted. The branch is `eng/inference-baseline-20260924`, unpushed.

Completed in this wave: signed-in public KILN-OK generation and health READY; public Stop, reload, Continue; a synthetic 20,032-token browser request delivered intact and answered its tail marker. This last result took 99.28 seconds to first token and added roughly 1.89 GiB of swapouts. The fixed two-corpus, 50-item semantic set has 50/50 offline evidence retention under the current packer, with 27 packed routes. It has no generated-answer score. The full backend test suite passed 294 tests. API code commit `53e6eac` was deployed after a fresh SQLite backup; a signed-in public POST-DEPLOY-OK reply was exact with TTFT 2,840 ms.

Direct MLX semantic pilots are recorded in `eval/compendium-pilot-L43.json` and
`eval/compendium-pilot-L01.json`. L43's packed route found the right `8 人`
but hit its 96-token output cap; L01's 21,088-token full route found the gold
sentence but included an unwanted preceding sentence. The pilot total times
are 46.799 and 107.473 seconds on different questions, so they are not a
paired speed comparison. The L01 call added 3,936 swapout pages; afterward
Swap free was about 877 MiB.

All 30 behavior prompts were rerun at temperature 0 with 512 output tokens
and recorded `finish_reason` in `eval/behavior-30-rerun.jsonl`. Twenty-seven
stopped normally; B25/B26/B30 hit the length cap. B08's wrong Beijing–London
conversion and B24's two sentences instead of three reproduced. G2 remains
failed on substantive quality despite no refusal opener.

Immediate next work:

1. Check current memory and swapouts before further GPU work. The most recent sample after L01 reported 15,507 MiB used and 877 MiB free. Avoid simultaneous long GPU jobs. The earlier synthetic browser request added about 1.89 GiB of swapouts.
2. Score the fixed 50 semantic questions through the deployed model, comparing full and packed routes on the same item only when memory pressure permits. Record strict answer, numeric value, unit, quote completeness, prompt tokens, TTFT, decode, and swapping. Do not label CPU evidence retention as answer quality.
3. Run controlled video pause and timed generator recovery; independently test 20,000 Chinese characters and 20,000 tokenizer tokens for semantic understanding, not only transport. Revisit the failed G1–G5, G7–G8 entries after measurement.

No disk deletion is qualified. Do not restart `com.kiln.mlx` for routine API deployment. Do not push without user request.

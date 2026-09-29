# CONTINUE_NEXT

Status: IN PROGRESS. Do not mark Kiln COMPLETE. The acceptance ledger is `acceptance.json`. The convergence note is `convergence-20260925.md`.

Production baseline: MLX PID 1581 on 8081, API PID 64536 on 8787 at commit `7a710f2`, public web asset `index-CJGbwbMg.js`. MLX has not been restarted. The branch is `eng/inference-baseline-20260924`, unpushed. Local health after this API restart is UNVERIFIED, AVAILABLE, provider reachable.

Completed in this wave: evidence checks run only when a request supplies evidence; the original model text and the reason are stored in `messages.metadata_json`; ordinary chat still has no `answer_check`. Targeted tests passed (21, then the full API file at 20). Chat DB backup `chat-before-answer-check-persist.db` passed `integrity_check`.

Not completed, and not retried: numeric difference, cross-section relation, and absent-fact refusal on `eval/semantic-20k.txt`. A direct MLX POST timed out. An idle 8-second sample showed Swapouts +8280 pages, with free swap about 915 MiB. Video pause stays unrun. Browser Stop, Continue, and session save remain the earlier public session, not a retest of PID 64536.

Do not start another long prefill, a second 9B, or `com.kiln.mlx` while swapouts are rising. Do not push without user request. No disk deletion is qualified.

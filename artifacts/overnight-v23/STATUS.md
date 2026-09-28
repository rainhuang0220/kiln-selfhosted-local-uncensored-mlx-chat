# Overnight V23 — status

- worktree: /tmp/kiln-night-v23 (branch night/immersive-v23 from 8d4821d)
- state: /tmp/kiln-night-v23-state.json (mirror: artifacts/overnight-v23/state.json)
- eval: worktree API on :8797 (runs/start-eval-api.sh, temp sqlite), harness runs/harness.py N, scorer runs/score.py N
- cycle sum = per-gate min over P1 (你好) and P2 (你靠近一点), max 12

## Cycles
| cycle | measured code | sum | G1 G2 G3 G4 G5 G6 | patch after |
|---|---|---|---|---|
| 1 | 8d4821d baseline | 4 | 2 1 0 0 1 0 | G4 loop guard + rep 1.08 floor |
| 2 | a68b0da | 4 (+hard fail: MLX died) | 2 1 0 0 1 0 | token-id continue-prompt dedupe (MLX crash); revert rep floor |
| 3 | 6f12e6a | 7 | 2 1 0 1 1 2 | sync #1 to live (120145f); style digest + grounded senses (68e1b0f) |
| 4 | 68e1b0f | 10 | 2 2 2 1 1 2 | next_beat fence on fill hops |
| 5 | e21b213 | 9 | 2 2 2 0 1 2 | refrain + cross-turn echo guard |
| 6 | 4964338 | 10 | 2 2 2 1 1 2 | echo reference on resume hops + short-line repeat guard |
| 7 | b39869a | 10 (P1 11) | 2 2 2 1 1 2 | stop: plateau |

## Stopped
3 consecutive cycles without beating 10. Best code b39869a. Next lever: continuation seam fragments after guard cuts (stray '平稳）' lines) and P2 length.

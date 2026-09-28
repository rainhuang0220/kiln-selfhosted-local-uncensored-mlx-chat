# Overnight V23 — status

- worktree: /tmp/kiln-night-v23 (branch night/immersive-v23 from 8d4821d)
- state: /tmp/kiln-night-v23-state.json (mirror: artifacts/overnight-v23/state.json)
- eval: worktree API on :8797 (runs/start-eval-api.sh, temp sqlite), harness runs/harness.py N, scorer runs/score.py N
- cycle sum = per-gate min over P1 (你好) and P2 (你靠近一点), max 12

## Cycles
| cycle | measured code | sum | G1 G2 G3 G4 G5 G6 | patch after |
|---|---|---|---|---|
| 1 | 8d4821d baseline | 4 | 2 1 0 0 1 0 | G4 loop guard + rep 1.08 floor |

## Next
Cycle 2: re-run P1/P2 on the cycle-1 commit; if G4 rises, next class is G2/G3 (nameless style digest on the IR default hop).

# Evidence index, 2026-09-25 19:42 CST

Authoritative labels are in `acceptance.json`. Narrative: `convergence-20260925.md`.

| Gate | Status | Where |
| --- | --- | --- |
| G0 | PASS | `live-deploy-20260925.md`; API-only restart to PID 64536 |
| G1 | PARTIAL | READY was observed earlier; current health is UNVERIFIED; video recovery not run |
| G2 | FAIL | `eval/behavior-audit.md`; B08 and B24 |
| G3 | FAIL | `convergence-20260925.md`; three semantic checks have no saved model answer |
| G4 | PARTIAL | `speed-paths.md`; one frozen three-path lookup |
| G5 | PARTIAL | browser Stop/Continue in `live-deploy-20260925.md`; full-text prefill is not 2× |
| G6 | PASS | `disk-dependency.md`, 30 protected, 0 deletions |
| G7 | PARTIAL | API is `7a710f2`; browser proof stops at `53e6eac` |
| G8 | FAIL | no independent recheck of `7a710f2` |

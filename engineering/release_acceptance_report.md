# release_acceptance_report.md

**Decision: READY WITH LIMITATIONS**

Date: 2026-09-26 (revalidation wave). Public: https://kiln.plainlist.space  
Delivered commit: `a4e172f6a133f6ac761b36d24036f511090502fa` · New tag: `v0.1.1-beta` (does **not** move `v0.1.0-beta` @ `7061166`)  
MLX verified PID **1581** @ **127.0.0.1:8081** (cmdline `mlx_lm.server`, host 127.0.0.1).

Labels: **OBSERVED** = retested this wave · **INHERITED** = prior evidence not re-run · **BLOCKED** = not run.

## Authentication

| Check | Label | Evidence |
| --- | --- | --- |
| Public login / refresh / logout / anon deny / authed chat | **OBSERVED PASS** | `mission-narrative-20260925/evidence/public-release/authz_observed_retest.json` |
| Account acquisition (CLI + UI copy) | **OBSERVED** | `owner-onboarding.md`; AuthGate `create-user` copy |
| Open signup | Disabled (by design) | `AUTH_SIGNUP=false` |

## Deployment / availability

| Check | Label | Evidence |
| --- | --- | --- |
| Six-state public probe | **OBSERVED** | `…/health_six_states_observed.json` |
| Tunnel interrupt recovery (SSH kill only) | **OBSERVED PASS** (~21s) | `…/tunnel_recovery_observed.json` — API+MLX PIDs unchanged |
| Prior 502 root cause | **OBSERVED** | tunnel listener lost while static stayed 200 |

## Runtime

| Check | Label |
| --- | --- |
| Local health / public readyz | **OBSERVED PASS** |
| MLX localhost-only | **OBSERVED PASS** |

## Long context / Narrative / Persona

| Check | Label |
| --- | --- |
| Phase 2 long-form / persona / Stop-Continue matrix | **NOT RUN — RESOURCE BLOCKED** |
| Reason | `should_pause_for_resources` → `low_pages_free` (~3929); see `memory_gate_observed.json` |
| Prior narrative 20637 visible / 18148 Han | **INHERITED** (not re-run) |

## Known limitations

1. Long-form/persona acceptance **BLOCKED** on host memory — do not kill MLX to free swap.  
2. R4 GPU 10–15Q incomplete (**INHERITED**).  
3. Uncensored safety boundaries (**INHERITED**).  
4. Public `/health` remains nginx 404; use `/readyz`.  
5. Tag `v0.1.0-beta` remains historical at `7061166`; delivered work is `v0.1.1-beta`.

## Decision rationale

**READY WITH LIMITATIONS** — public entry, authz, and tunnel recovery are OBSERVED. Model-quality long-form/persona remain RESOURCE BLOCKED, not silently replaced with smaller tests.

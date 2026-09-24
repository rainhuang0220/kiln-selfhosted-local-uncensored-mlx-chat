# Kiln 2026-09-24 coordination

Orchestrator owns production changes, model benchmarks, disk deletion, and git commits.

## Locks

- No agent restarts LaunchAgents or touches ports 8081 / 7777 / 8787 listeners.
- No agent edits kiln source, plists, launch scripts, or env files.
- No agent deletes files. Cleanup is plan-only until the orchestrator runs it.
- No agent sends generation requests. GET health/models is allowed when it does not generate.
- Benchmarks wait for `engineering/2026-09-24/ALLOW_BENCH` created by the orchestrator.
- Each agent writes only its own file under `agents/` plus raw logs under `raw/<agent>/`.
- Do not print secrets. Image, video, and unconfirmed Qwen 3B / small-transformer files stay protected.

## Live facts at dispatch (verify, do not trust)

- Kiln git: `/Users/rainhuang/Desktop/models/kiln`, branch `ui/account-menu-placement`, HEAD `0a4322d`.
- MLX listener: Python PID 1581, `127.0.0.1:8081`, LaunchAgent `com.kiln.mlx`, runs=6.
- Historical inference work lived on `feat/conversational-reliability` (`a6a4d2e`). It may not be this HEAD.
- Public host `kiln.plainlist.space` auth hardening must not be weakened.

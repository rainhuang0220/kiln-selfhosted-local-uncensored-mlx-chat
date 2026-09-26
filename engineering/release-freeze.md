# Kiln production freeze — 2026-09-26

## Snapshot

| Field | Value |
| --- | --- |
| Branch | `eng/inference-baseline-20260924` |
| HEAD | `21fef2e` (auth gate + release docs; tag `v0.1.0-beta` remains on `7061166`) |
| Release tag | `v0.1.0-beta` → `7061166` |
| Public URL | https://kiln.plainlist.space |
| API | `127.0.0.1:8787` (uvicorn) |
| Web (local) | `127.0.0.1:7777` (Vite; not public origin) |
| Public path | VPS nginx static + reverse tunnel `127.0.0.1:17777` → Mac `:8787` |
| MLX | PID **1581**, bind **127.0.0.1:8081** only |
| Database | `kiln/data/chat.db` (mode 0600) |
| Migrations | through `0006_narrative_continue` |
| Backup | `kiln-backups/narrative-mission-r5-20260926-024013/` |

## Current capabilities

- Private-mode auth wall on the public hostname (`KILN_EXPOSURE=private`)
- Owner-issued accounts via local CLI (`create-owner`, `create-user`); no public self-signup
- Chat, context routing, evidence verification, narrative engine + `/narrative/continue`
- Resource pause on low free swap / pages free (does not kill MLX)

## Known limitations

- R4 GPU 10–15Q benchmark incomplete (low pages free)
- Uncensored model safety boundaries
- Public `/health` intentionally nginx 404
- Long-form / multi-turn acceptance paused under memory pressure this wave
- Tunnel can drop (502 on API routes) until `com.kiln.web-tunnel` recovers

## Rollback

1. DB: restore `kiln-backups/narrative-mission-r5-20260926-024013/`
2. API only: `launchctl kickstart -k gui/$(id -u)/com.kiln.api`
3. Tunnel only: `launchctl kickstart -k gui/$(id -u)/com.kiln.web-tunnel`
4. Static: rsync previous `web/dist` to VPS `/www/wwwroot/kiln.plainlist.space/`
5. **Never** restart or rebind MLX (PID 1581)

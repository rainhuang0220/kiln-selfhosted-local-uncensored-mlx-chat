# Kiln production freeze — 2026-09-26 (revalidated)

## Snapshot

| Field | Value |
| --- | --- |
| Branch | `eng/inference-baseline-20260924` |
| Delivered HEAD | *(see `v0.1.1-beta` tag)* |
| Historical tag | `v0.1.0-beta` → `7061166` (**not moved**) |
| New tag | `v0.1.1-beta` |
| Public URL | https://kiln.plainlist.space |
| API | `127.0.0.1:8787` |
| Public path | VPS nginx + SSH tunnel `17777→8787` |
| MLX | PID **1581**, **127.0.0.1:8081** only (verified) |
| Database | `kiln/data/chat.db` |
| Migrations | through `0006_narrative_continue` |
| Backup | `kiln-backups/narrative-mission-r5-20260926-024013/` |

## Current capabilities

- Private auth; owner-issued accounts (`create-user` CLI)
- `/readyz` public readiness (no generation)
- Tunnel reconnect with backoff; launchd KeepAlive
- Narrative engine + continue API (code present; long-form QA may be RESOURCE BLOCKED)

## Known limitations

- Long-form/persona acceptance: **NOT RUN — RESOURCE BLOCKED** when `low_pages_free`
- Uncensored safety boundaries
- Public `/health` nginx 404 — use `/readyz`

## Rollback

1. DB backup restore  
2. API: `launchctl kickstart -k gui/$UID/com.kiln.api`  
3. Tunnel: `launchctl kickstart -k gui/$UID/com.kiln.web-tunnel`  
4. Never restart MLX for tunnel/API issues  

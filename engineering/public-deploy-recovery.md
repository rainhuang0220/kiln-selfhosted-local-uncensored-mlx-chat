# Public deploy and recovery runbook

## Path

Browser → `https://kiln.plainlist.space` (VPS nginx static + API proxy) → `127.0.0.1:17777` (SSH reverse) → Mac Kiln API `127.0.0.1:8787` → MLX `127.0.0.1:8081`.

| Edge | Process | Auth boundary | Failure mode |
| --- | --- | --- | --- |
| Public TLS | nginx on VPS | none (static) | homepage still 200 when API down |
| API proxy | nginx → 17777 | session/bearer at API | **502** when tunnel/listener gone |
| Tunnel | `com.kiln.web-tunnel` / `run-web-tunnel.sh` | SSH key | listener lost; reconnect with backoff |
| API | `com.kiln.api` uvicorn | Argon2id session | local health fails |
| Model | `com.kiln.mlx` mlx_lm.server | localhost only | MODEL_AVAILABLE false; never expose 8081 |

## Health (six states)

```bash
./scripts/public-health-probe.sh
# or read https://kiln.plainlist.space/readyz (no generation)
```

- `STATIC_UP` — homepage 200  
- `PUBLIC_API_UP` — `/readyz` or `/auth/status` 200 via public origin  
- `AUTHENTICATION_UP` — `/auth/status` JSON  
- `BACKEND_UP` — local `/health`  
- `MODEL_AVAILABLE` — MLX HTTP alive (no generate)  
- `END_TO_END_CHAT_UP` — requires authenticated chat smoke  

Homepage 200 alone is **not** availability.

## Tunnel-only recovery (do not restart API/MLX)

```bash
launchctl kickstart -k "gui/$(id -u)/com.kiln.web-tunnel"
```

Script path: `scripts/run-web-tunnel.sh` (synced to `~/Library/Application Support/kiln/run-web-tunnel.sh`).  
launchd: `KeepAlive=true`, reconnects after SSH child death with exponential backoff + stale-port reclaim.

## API-only restart (rare)

```bash
launchctl kickstart -k "gui/$(id -u)/com.kiln.api"
```

## Never

- Restart MLX to “fix” a 502  
- Bind MLX to `0.0.0.0` or open 8081 publicly  
- Replace live nginx vhost with a cert-less template

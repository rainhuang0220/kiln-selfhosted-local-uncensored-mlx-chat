# Monitoring / health

## Unauthenticated endpoints

| URL | Purpose |
| --- | --- |
| `GET /readyz` | Backend + auth readiness + model HTTP; `generates:false`; never claims E2E chat |
| `GET /auth/status` | Auth gate metadata |
| `GET /health` | Full gateway snapshot (local / private; **public nginx returns 404** by design) |

## Probe

`scripts/public-health-probe.sh` aggregates six states from the public origin + local health.

## Alerting cues (manual)

- Homepage 200 + `/auth/status` 502 → tunnel/API path down (STATIC_UP only)  
- `/readyz` MODEL_AVAILABLE false → MLX HTTP down (do not force GPU)  
- Repeated `STATE=REMOTE_LISTENER_LOST` in `/tmp/kiln-web-tunnel.err` → tunnel flapping

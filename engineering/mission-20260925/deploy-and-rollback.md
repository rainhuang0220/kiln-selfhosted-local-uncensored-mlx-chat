# API deploy and rollback, 2026-09-25

MLX was not restarted. PID 1581 listened on 127.0.0.1:8081 before and after every API restart.

Database backup before the first restart of this wave:

`/Users/rainhuang/Desktop/models/kiln-backups/2026-09-25/chat-before-486d774.db`

`PRAGMA integrity_check` on the live database and on that backup both returned `ok`.

## Forward

`launchctl kickstart -k gui/501/com.kiln.api` while the tree was `486d774`.

The new API was PID 82377. `GET /health` returned `reachable=true`, `gateway.state=AVAILABLE`, `inference_capability=UNVERIFIED`, `inference.ready=false`, `verification_method=null`, `evidence_expires_at=null`.

## Back

`git switch --detach c22d1c3`, then the same kickstart.

Health had no `inference_capability`. `inference.ready` was `true`. `gateway.state` was `AVAILABLE`. MLX stayed 1581.

## Forward again

`git switch eng/inference-baseline-20260924`, then the same kickstart.

The API is PID 82691. Health again shows `UNVERIFIED` and `ready=false`. The working tree is `486d774`.

Rollback command if this API build misbehaves:

```bash
cd /Users/rainhuang/Desktop/models/kiln
git switch --detach c22d1c3
launchctl kickstart -k "gui/$(id -u)/com.kiln.api"
```

Return:

```bash
git switch eng/inference-baseline-20260924
launchctl kickstart -k "gui/$(id -u)/com.kiln.api"
```

Do not include `com.kiln.mlx` in either command.

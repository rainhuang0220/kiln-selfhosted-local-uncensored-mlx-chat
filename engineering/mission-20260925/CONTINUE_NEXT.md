# CONTINUE_NEXT

Status: MISSION BLOCKED. Not COMPLETE.

Git: `eng/inference-baseline-20260924` at `486d774` until the ledger commit that follows this file. Not pushed.

Running: MLX PID 1581, API PID 82691 on `486d774`, web PID 97771.

Passed: G0 API rollback. Live health returns `inference_capability=UNVERIFIED` and `ready=false` while `reachable=true`.

Blocked:

1. Further GPU work. The 16-token MLX call wrote about 5.93 GiB of swap pages and grew the swap file by 2 GiB. Do not start a 20k prefill until a 60 second sample shows swapouts flat and a second 16-token call adds near-zero swapouts.
2. Kiln-mediated READY, browser Stop/Continue, and public SSE. `POST /chat` is 401. `api.env` has no bootstrap password. Do not search the disk for a password. The next human step is to log in once in the browser at `http://127.0.0.1:7777` or provide a session.

Next command after a human session exists, and only if swapouts stay flat:

```bash
# one authenticated max_tokens=16 chat, then GET /health
# expect inference_capability READY and verification_method user_generation
```

Do not run `launchctl kickstart` on `com.kiln.mlx`.

Rollback of the API remains `c22d1c3`, documented in `deploy-and-rollback.md`.

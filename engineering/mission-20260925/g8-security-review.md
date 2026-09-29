# G8 security review (independent)

Date: 2026-09-25  
Reviewer posture: independent pass; did not author the recent exposure/auth changes.  
Scope commit at review time: working tree `8571a4b` (ledger target remains `7a710f2`; this note is a security surface review, not a full multi-gate live recheck).  
Constraints: read-only. No MLX `:8081` calls. No chat completions.

## Verdict: **PARTIAL**

No Critical / P0 auth-bypass or Host-based mode-selection defect in the reviewed code path. Private-mode fail-closed, CSRF origin allowlist, loopback bind, and MLX host allowlisting hold under static review and existing unit tests. Release is **not blocked** by an auth rewrite, but residual High/Medium risks remain (MLX reverse-tunnel to VPS loopback; Docker nginx XFF append). Treat those as **accepted residual risk** only if the documented nginx public path stays in force and the alternate compose/Caddy+8081 path is unused or equally locked down.

## Critical

_None._

## High

1. **Unauthenticated MLX exposed on VPS loopback via SSH `-R 8081`**  
   - Paths: `~/Library/LaunchAgents/com.kiln.mtplx-tunnel.plist`, mirrored `scripts/com.kiln.mtplx-tunnel.plist` (gitignored), tracked snapshot `engineering/2026-09-24/raw/A2/02-plist-com.kiln.mtplx-tunnel.plist`; described in `engineering/2026-09-24/agents/A11-tunnel-caddy.md`.  
   - Bind: `127.0.0.1:8081:127.0.0.1:8081` to `ubuntu@175.24.134.228`.  
   - Impact: any process on the VPS that can reach `127.0.0.1:8081` gets the raw MLX OpenAI-compatible API and bypasses Kiln session/Bearer auth, CSRF, and rate limits. Public nginx does not proxy `:8081`, so this is not an internet open port by itself; it widens the VPS trust boundary beyond “API-only tunnel to `:17777`”.  
   - Blocks release?: **No**, if public traffic stays on `deploy/nginx-kiln.plainlist.space.conf` → `:17777` → Mac `:8787` and VPS admin access is trusted. **Yes** if the release claims “8081 never leaves the Mac” without caveat.  
   - Smallest remediation (optional, not an auth rewrite): unload/disable `com.kiln.mtplx-tunnel` when the nginx+17777 path is the only live public path; keep compose’s 8081 tunnel only when compose/Caddy is intentionally in use.

## Medium

1. **Docker/`web/nginx.conf` appends client `X-Forwarded-For`**  
   - Path: `web/nginx.conf` (`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`).  
   - Contrasts with production `deploy/nginx-kiln.plainlist.space.conf` (`$remote_addr` overwrite) and `SECURITY.md` (overwrite, do not append).  
   - Impact: if compose is deployed with `TRUST_PROXY_HEADERS=true`, rate-limit IP (`auth.py` uses `X-Real-IP`, which is set to `$remote_addr` in that file — partially mitigated) still depends on proxy correctness; the append pattern is the wrong default for any future consumer of `X-Forwarded-For`.  
   - Blocks release?: **No** for the documented plainlist nginx path. Residual for compose/Caddy alternate.

2. **Tracked engineering artifacts disclose VPS identity and tunnel layout**  
   - Paths: `engineering/2026-09-24/raw/A2/02-plist-com.kiln.*.plist`, `A11-tunnel-caddy.md`, related raw notes.  
   - Contents include public VPS IP `175.24.134.228`, `ubuntu@` / `kiln-tunnel@` accounts, listen maps (`17777`↔`8787`, `8081`↔`8081`). No private keys or live passwords observed in git.  
   - Blocks release?: **No**. Residual reconnaissance aid; keys remain mode `600` under `Application Support/kiln/`.

3. **Client-supplied `evidence` can rewrite stored assistant text (authenticated)**  
   - Paths: `backend/app/main.py` (`ChatBody.evidence`, max 20 000 chars), `backend/app/services/chat.py` (apply `verify_answer`), `backend/app/services/answer_verify.py`.  
   - Not filesystem path injection: evidence is an inline string, not a path.  
   - Impact: a caller who can already chat (cookie/CSRF-ok or Bearer) can force answer substitution when verification marks the model wrong. Integrity of transcripts for eval/API abuse, not anonymous RCE.  
   - Blocks release?: **No**. Accepted for the eval/correctness feature; optional later gate: ignore `evidence` unless a dedicated owner/eval flag is set.

4. **Unauthenticated `/health` on the API process**  
   - Paths: `backend/app/auth.py` (`path == "/health"` public), `backend/app/main.py` (handler also bound as `/auth/runtime`).  
   - Public nginx returns 404 for `/health`; `/auth/runtime` requires auth in private mode (not in `PUBLIC_EXACT`). Direct callers of VPS `127.0.0.1:17777` still get anonymous health (private mode blanks `provider.base_url`).  
   - Blocks release?: **No**. Matches `SECURITY.md` / takeover notes. Residual status leakage on the tunnel socket.

## Low

1. **Local-mode CSRF skipped for `/chat` when unauthenticated** — by design (`auth.py` CSRF only when `private` or authed or `/auth/*`). Safe only because local mode forbids non-loopback Host / forwarded HTTPS / public `X-Forwarded-Host`.  
2. **Default `cors_origins` string still lists `https://kiln.plainlist.space`** (`config.py`) — filtered out of local allowlists (http+loopback only); private mode uses `KILN_PUBLIC_ORIGIN` alone. Dead string, not a mode switch.  
3. **OpenAPI/docs disabled when private or bootstrap credentials present** — good; local ungated docs remain loopback-only by host policy.

## What was checked

| Area | Result |
| --- | --- |
| `exposure_for` / mode selection | Config-only via `KILN_EXPOSURE`; Host / `X-Forwarded-*` / `user_count` do not select mode (`security.py`, tests in `test_explicit_exposure.py`) |
| Local tripwire | Public Host, LAN Host, `X-Forwarded-Host`, `X-Forwarded-Proto: https` → `403 local_mode_violation` |
| Private fail-closed | Auth required even on loopback Hosts and with zero users (`not_ready` / `401`); signup disabled path covered by tests |
| Startup invariants | Unset exposure refuses start; private requires `COOKIE_SECURE` + https `KILN_PUBLIC_ORIGIN`; `APP_HOST` must be loopback |
| CSRF | Cookie POSTs need allowlisted Origin; Bearer skips CSRF intentionally |
| Cookies | Private uses `__Host-kiln_session`, `Secure`, `HttpOnly`, `SameSite=strict`, path `/` |
| SSE `/chat` and `/v1/chat/completions` | Same `AuthRateMiddleware` gate as other routes; private anonymous → 401/503 (unit-tested for completions; streaming uses same middleware before handler) |
| SSRF (MLX) | `mlx.py` allowlists loopback/`host.docker.internal`; `follow_redirects=False`; URL from settings only |
| Open redirects | No `RedirectResponse` / user-controlled redirect targets in app code |
| `answer_verify` / evidence | String-only verification; no `Path`/`open`/`../` resolution |
| Media file serve | `output_path` constrained with `resolve().relative_to(generations_dir)` |
| Model activate | `model_id` regex; `subprocess.run([script, path, model_id], …)` no shell |
| Secrets in repo | `deploy/.env` gitignored; plists under `scripts/` gitignored; no private keys tracked; `api.env` / `kiln-tunnel` are `0600` outside the repo |
| LaunchAgents / tunnels | Web tunnel binds `127.0.0.1:17777`→`8787`; mtplx binds `8081` (see High); live `api.env` shows `KILN_EXPOSURE=private`, `COOKIE_SECURE=true`, `TRUST_PROXY_HEADERS=true`, `KILN_PUBLIC_ORIGIN=https://kiln.plainlist.space` |
| Public nginx assumptions | Documented in `SECURITY.md`, `deploy/nginx-kiln.plainlist.space.conf`, A11 notes: static `web/dist`, API proxy overwrite of `X-Real-IP`/`X-Forwarded-For`, `/health`/`/docs` 404, SSH `-R` listen on VPS loopback only |

## Out of scope

- Live public HTTPS probing, browser session theft, or signed-in chat on `kiln.plainlist.space`  
- Calling MLX `:8081` or sending completions (explicitly forbidden for this pass)  
- Full G0–G7 functional/performance revalidation (G8 ledger “every gate” is broader than this security note)  
- VPS-side `ss`/nginx live file confirmation (A11 already marked NOT OBSERVED)  
- Prompt-injection / model content safety  
- Full dependency CVE scan, SQLite encryption at rest, FileVault / stolen-Mac scenarios (`SECURITY.md` “What we do not claim”)  
- Rewriting the auth system

## Release gate vs residual risk

| Finding | Release block? | Classification |
| --- | --- | --- |
| Host-based exposure / anonymous private open | N/A — not present in current code | Prior class of bug; fixed and covered by tests |
| MLX `:8081` reverse tunnel to VPS | No (with nginx-only public path + trusted VPS) | High residual; disable tunnel if unused |
| `web/nginx.conf` XFF append | No for plainlist nginx | Medium residual for compose |
| Repo VPS IP / tunnel docs | No | Medium info disclosure |
| Client `evidence` rewrite | No | Medium integrity (authed) |
| Anonymous API `/health` on tunnel | No | Medium/Low; nginx 404 on public |

**P0 remediations:** none required for this verdict.  
**Optional smallest hardening:** unload `com.kiln.mtplx-tunnel` if compose/Caddy is not the live edge; align `web/nginx.conf` XFF with `$remote_addr` if compose remains supported.

## Evidence pointers

- Code: `backend/app/security.py`, `auth.py`, `config.py`, `main.py`, `providers/mlx.py`, `services/answer_verify.py`, `services/media.py`  
- Tests: `backend/tests/test_explicit_exposure.py`, `test_security_invariants.py`  
- Policy/deploy: `SECURITY.md`, `deploy/nginx-kiln.plainlist.space.conf`, `engineering/2026-09-24/agents/A11-tunnel-caddy.md`  
- Runtime (read-only file inspect): `~/Library/Application Support/kiln/api.env` → private exposure settings present

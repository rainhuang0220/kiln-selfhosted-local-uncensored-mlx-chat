# Security policy

Kiln is a private local AI. It is not an “absolutely secure” hosted product. The threat model is: keep transcripts, memories, and generated media on the Mac, require explicit login on any internet hostname, and keep the public surface small.

## Supported configuration

### Local development

- Bind API, UI, and MLX to `127.0.0.1` only.
- `KILN_EXPOSURE=local` may allow use with zero accounts on loopback.
- Vite is a development server. Do not point a public reverse proxy at it.

### Private internet deployment

- HTTPS only. HTTP must redirect to HTTPS.
- `KILN_EXPOSURE=private`
- `COOKIE_SECURE=true`
- `TRUST_PROXY_HEADERS=true` only behind a reverse proxy that **overwrites** `X-Real-IP` / `X-Forwarded-For` with the connecting client (do not append client-supplied values).
- Auth is always required. An empty users table is **not** an open app. Create the first owner on the Mac:

  ```bash
  cd backend && ../.venv/bin/python -m app.cli create-owner --username YOURNAME
  ```

- `AUTH_SIGNUP` stays false. The first public visitor must not become the owner.
- Public vhost serves `web/dist` and proxies API routes to a **loopback** SSH reverse tunnel into Mac `:8787`.
- Public ports: 80 and 443. Do not publish 7777, 8787, 8081, or 17777.
- SSH `-R` bind address must be `127.0.0.1`. Production uses a dedicated `kiln-tunnel` account: `AllowTcpForwarding remote`, `PermitListen 127.0.0.1:17777`, `GatewayPorts no`, no PTY/X11/agent. `ubuntu` remains the admin login so SSH cannot be locked out.
- Model download/activate is owner-only. Prefer keeping model management off the public proxy if you do not need it remotely.

`deploy/.env`, SQLite files, TLS certificates, model weights, chat transcripts, and session records are runtime data. They must never be committed, uploaded to a public repository, or shared in an issue.

## What we do not claim

- FileVault off, an unlocked Mac, a stolen session cookie on a remembered device, or a compromised VPS admin panel are outside this baseline.
- SameSite is not the only CSRF control. Cookie-authenticated POST/PATCH/DELETE require an allowlisted `Origin`.
- Browser session cookies are not long-lived API keys. Use `python -m app.cli create-api-token` for Bearer access.

## Reporting a vulnerability

Please use GitHub's private security-advisory flow for this repository. Do not open a public issue for a suspected credential leak, authentication bypass, data exposure, or remote-code-execution vulnerability.

Include the affected release, a minimal reproduction, impact, and any safe mitigation you identified. We will acknowledge reports and coordinate a fix before disclosure.

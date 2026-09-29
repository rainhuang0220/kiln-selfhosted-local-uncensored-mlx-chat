# AUTH_ARCHITECTURE_REPORT.md

## Product judgment

Kiln at `https://kiln.plainlist.space` is a **personal private AI** exposed for **owner remote access**, released as `v0.1.0-beta`. Evidence: `KILN_EXPOSURE=private`, `AUTH_SIGNUP=false`, UI kicker “Kiln / Private”, auth status `exposure:"private"`, `signup:false`. It is **not** an open multi-tenant public beta with self-serve registration.

Registration strategy chosen: **owner-issued accounts (invite-offline / CLI)** — closest to option **C** without building an invite-token product. Open registration (B) was rejected for an uncensored model on a public hostname. First-visit admin init (A) already completed (owner `rain` exists).

## Architecture (Browser → Login → API → DB → Session → Chat)

1. **Browser** loads static UI from VPS nginx (`/www/wwwroot/kiln.plainlist.space`).
2. **AuthGate** calls `GET /auth/status` (proxied `nginx → 127.0.0.1:17777 → Mac:8787`).
3. **Login** `POST /auth/login` verifies Argon2id password hash in SQLite `users` table; creates row in `sessions`; sets `__Host-kiln_session` (Secure, HttpOnly, SameSite=strict) when `COOKIE_SECURE=true`.
4. **Protected APIs** (`/chat`, `/conversation`, `/narrative`, …) require a valid session cookie or bearer token; anonymous → `401 auth_required`.
5. **Account types**: SQLite user table (not a single hardcoded password). Roles: first user `owner`, later users `user`. Bootstrap via local CLI only.

### Single-user password vs DB vs bootstrap vs registration

| Mechanism | Present? | Notes |
| --- | --- | --- |
| Single shared public password | No | Forbidden / not used |
| DB user table | Yes | `users.password_hash` Argon2id |
| Admin bootstrap | Yes | `python -m app.cli create-owner` (local only; refuses if owner exists) |
| Public registration | Disabled | `AUTH_SIGNUP=false`; status always `signup:false` under private mode |
| Owner-issued extra users | Yes (this wave) | `python -m app.cli create-user --username NAME` (local only) |

## Why the public site could not be logged into (root cause)

**Diagnose-first findings (ordered):**

### 1) P0 outage — API tunnel down (primary blocker at mission start)

- **Symptom:** `GET https://kiln.plainlist.space/auth/status` → nginx **502**; homepage static still **200**.
- **Evidence:** VPS `ss` showed **no** `127.0.0.1:17777` listener; `/tmp/kiln-web-tunnel.err` had `REMOTE_LISTENER_LOST`, `remote port forwarding failed for listen port 17777`, intermittent `ROUTE_OK_TCP22_FAIL`. Local API `:8787/health` remained **200**.
- **Root cause:** SSH reverse tunnel (`com.kiln.web-tunnel`) had lost the remote forward; nginx could serve HTML but could not reach Kiln API / auth.
- **Fix applied:** reclaim stale remote port + `launchctl kickstart -k …/com.kiln.web-tunnel` (**tunnel only**; MLX untouched). After fix: public `/auth/status` → 200 JSON.

### 2) Product auth policy — no public self-serve account path

- **Symptom:** Even with tunnel healthy, a **new** visitor sees login only (`signup:false`, `setup:false`, `ready:true`).
- **Evidence:** Live env keys (names only): `KILN_EXPOSURE=private`, `AUTH_SIGNUP=false`. DB: exactly one owner user `rain`. Backend: private mode forces `signup = auth_signup and not private` → always false when private. UI `AuthGate` only calls `register` when `authSetup` (zero users).
- **Root cause:** By design, public self-registration is off. Prior “EXTERNAL BLOCKER” was partly “agent lacks owner password”, but the deeper product truth is: **accounts are owner-issued**, not open signup. The login page previously did not state how to obtain an account.

### 3) Not the root cause (checked)

- Password hash algorithm mismatch: Argon2id verify path intact; wrong password returns clear `auth_failed`.
- Missing initial user: owner exists (`user_count=1`).
- Cookie scheme: public login sets `__Host-kiln_session` successfully after tunnel restore.
- Database path mismatch: API uses `kiln/data/chat.db` (same file CLI mutates).

## How a real user gets an account (true in product + docs)

1. Owner on the Mac runs: `python -m app.cli create-user --username NEWUSER` (password via prompt / `KILN_NEW_USER_PASSWORD`; never commit).
2. Or first-time machine: `python -m app.cli create-owner --username YOURNAME`.
3. Login at https://kiln.plainlist.space with that username/password.
4. Login page copy (deployed) states: private remote access; new accounts via local `create-user`; **no public self-registration**.

## Human private step (owner)

If the owner forgot the `rain` password: on the Mac only, `python -m app.cli reset-password --username rain` (local recovery; not over the public internet). Do not put the password in git or chat logs.

## Phase 1 proof account

- Username: `qa_release` (role `user`), created via legitimate `create-user`.
- Password file: `~/Library/Application Support/kiln/qa-release.credentials` mode **0600** (not in git).
- Public acceptance evidence: `engineering/mission-narrative-20260925/evidence/public-release/phase1_auth_acceptance.json` (`phase1_pass: true`).

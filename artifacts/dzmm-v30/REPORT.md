# DZMM V30 provider and billing report — 2026-09-29

- HEAD before: `8ab59bc`; code HEAD after: `69f2b06` on `feat/immersive-dialogue`. `main` and the draft state of PR #6 were not changed.
- Token configured: no. No Token value was printed or committed. Live NaLang smoke was skipped because neither `KILN_DZMM_TOKEN` nor the local DZMM settings file exists.
- `/v2/models` reachable: yes, public endpoint returned HTTP 200. The visible NaLang rows had no `price` or `pricing` field; Kiln shows `见充值页` and `估价，以钱包为准`.
- Default model in UI: `local:9b` without a Token; `nalang-turbo-0826` after a Token is saved. XL is labeled `推荐付费 / 文爱更好` and is never selected automatically.
- Preset → card: the bundled parlor fixture is 270 characters. It maps to a 275-character card description, 52-character scene, and empty first message. A 3,000-character source test clips description to 2,400 and excludes `EVENT_LEDGER` and school memories. Named recall includes only events for the requested person.
- Card import: Tavern V2 JSON and PNG `chara` metadata passed tests; local search and tag filtering are available. The probed DZMM character page returned HTML, so URL import asks for JSON/PNG export.
- Backend tests: 628 passed, 5 skipped (full suite before the quota-body follow-up); the final V30-focused run passed 11 tests, and 34 affected tests passed. Frontend: 77 passed; TypeScript and Vite build passed. The final build was published assets first, then `index.html`.
- Runtime: API-only kickstart produced PID `46869`; `/health` reports `immersive / 6144`. `:8081` still serves `qwen3.5-9b-hauhau-aggressive-mxfp4`, and a direct 8-token `好` returned 8 completion tokens. Public `/readyz` returned 200 after the existing reverse tunnel reconnected.
- Limitation: cloud response quality, actual wallet balance, and live card acceptance cannot be verified without the owner's DZMM Token. If the owner switches the single local MLX server to 27B, it must be switched back to 9B to preserve the stated 9B quota fallback.

recharge URL shown in Settings? yes — `https://www.dzmm.ai/` with the official `去充值` path and payweld.com entry note.

turbo is free-tier default when token present? yes — API and UI tests cover the default; daily quota is labeled `以官网当日配额为准`.

402 falls back to local 9B? yes — same-send stream tests cover 402 and 429, plus an HTTP 400 quota body, while 9B is the active local model; live cloud quota response remains untested without a Token.

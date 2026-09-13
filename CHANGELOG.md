# Changelog

## Unreleased

## v0.6.4 — CI uses repo-root npm test

- GitHub Actions `verify` runs `npm test` from the repository root so pytest uses the root `.venv`.

## v0.6.3 — CI test runner cwd

- `npm test` no longer `cd`s into `backend` before the frontend suite, so Ubuntu CI can finish after pytest.

## v0.6.2 — CI isolation for the private-mode gate

- Injected TestClient chat no longer runs live MLX restore, so Ubuntu CI cannot mark chat `recovery_failed`.
- Hub preflight tests enable downloads explicitly. MLX-only and local-tokenizer tests skip on hosts that lack those files.

## v0.6.1 — Final hardening

- Local-open mode is limited to loopback Hosts (`127.0.0.0/8`, `::1`, `localhost`). RFC1918 and link-local Hosts fail closed with zero users.
- Trusted HTTPS proxy requests cannot inherit local-open by spoofing `Host: 127.0.0.1`.
- Tokenizer load defaults to `trust_remote_code=false`.
- `python -m app.cli change-password` rotates an owner password and revokes sessions.
- Public nginx now writes a kiln-only access log (no cookies/bodies).
- Reverse SSH uses a dedicated `kiln-tunnel` user with `PermitListen 127.0.0.1:17777`.

## v0.6.0 — Private mode and conversational reliability

- Private internet mode is fail-closed: auth is required even with zero users, public Host cannot inherit local open mode, and the first owner is created on the Mac CLI.
- Browser sessions default to a non-persistent cookie with idle and absolute timeouts; “keep me logged in” is an explicit 7-day choice.
- Cookie-authenticated POST/PATCH/DELETE require an allowlisted Origin. Sibling subdomains are not trusted.
- Memory/conversation/generation queries fail closed without an owner. Legacy null-owner rows are assigned only at bootstrap.
- Model download/activate is owner-only. Public deployment serves `web/dist` and an API-only loopback tunnel, not Vite.
- Prompt-cache attribution for mlx-lm 0.31.3: per-request `chat_template_kwargs` does not bypass the LRU when token IDs match; streaming persists the same cache as non-streaming.
- Continue sends `/v1/completions` with a tokenizer-native prefix. mlx-lm 0.31.3 dies on an exact prompt-cache hit; Kiln drops the last token and, on retry, further tokens so the same prefix is not resent. Think-cut uses the same shortening. A leftover exact hit can still kill the generate thread; a silent Continue EOF counts as an inference fault.
- Mid-think Continue uses the official thinking generation prefix plus saved reasoning, not Kiln-built think tags.
- Continue/Regenerate HTTP errors before `meta` no longer remove the last turn from the local UI.
- Dialogue fold runs only when the prompt exceeds the hard profile budget. `prompt_soft_target` is occupancy metadata, not a fold trigger.
- Interactive Dialogue hard prompt cap is 10240 (soft target 8192). Balanced 16384; Reasoning keeps 32768.
- `/health` distinguishes MLX HTTP liveness from inference readiness after repeated timeouts.
- Offline CJK quality metrics and a non-CI long-dialogue evaluation runner.
- 250-turn Interactive Dialogue eval used `max_tokens=192`: warm TTFT p50 1.37s is a cache-hit floor (~96%), not a miss. Everyday/short-reply semantic repetition remains.
- Classify every generation terminal; incomplete upstream streams are no longer stored as a normal stop.
- Interactive Dialogue is the default profile: thinking off, a single `/v1/chat/completions` pass, max output 1536.
- Manual think-cut continuation is opt-in only (`thinking_continuation`), not the default chat path.
- MLX sampling controls (min_p, presence/frequency/repetition penalties and context sizes) are wired through Settings → API → provider.
- Long chats now fold complete turns into a rolling dialogue state/summary instead of first-160-character snippets.
- Memory search and `/memory` are owner-scoped. Retrieval receives a real conversation id.
- SSE heartbeats fire while waiting for the first provider event without cancelling the generator.
- Frontend shows TTFT vs decode tok/s, incomplete-generation copy, Continue, and collapsed advanced sampling.
- OpenAI-compatible streaming classifies EOF/malformed frames instead of emitting a silent successful `[DONE]`.
- Continue resumes an unclosed think block instead of forcing `</think>`.

- Split refusal/censorship claims from prompt-adherence quality. Document each backend’s checkpoint provenance instead of calling Kiln “fully uncensored.”
- Chat sampling now follows the Qwen3.5 card: thinking `0.6/0.95/20`, non-thinking `0.7/0.8/20`, with UI overrides.
- Image and video can compile prompts locally through the running Qwen (enhance before parking chat). Raw mode still sends the user text unchanged.
- Generation cards show Original vs Effective prompt, backend, model, seed, and steps.
- Video Fast keeps the old speed preset; Quality uses more steps, guide 6, shift 8, TeaCache off. Wan2.2 5B is not added on 24GB.

## v0.5.0

- Added local image/video generation with persistent jobs, cancellation, and serialized heavy workers.
- Added chat parking/recovery while video generation uses unified memory.
- Kept the v0.4 Model Workbench and local model activation flow.
- Standardized the local UI entrypoint at `http://127.0.0.1:7777`.
- Added optional reverse-proxy Host allowlisting so a public HTTPS front can reach the loopback UI.
- Documented measured M4 24GB video defaults and scaling limits.

## v0.4.0

- Added the Model Workbench: browse the live Hugging Face catalogue in Kiln, inspect repositories, download MLX-ready checkpoints into a private local library, and select the active model.
- Rebuilt the conversation surface around a compact kiln-room visual system: generated background art, collapsible history, per-conversation delete, message quote/delete, and a context-budget inspector.
- Made model selection restart-safe on the local host and added server-side MLX validation, safe Hub outage handling, activation checks, and deployment safeguards that keep public instances read-only.

## v0.3.0

- Made Kiln model-flexible while making the verified Qwen3.5-9B MLX profile the default.
- Added pinned, checksum-verified model download instructions; removed the unused 27B tokenizer from public deployment.

## v0.2.4

- Added CI validation of the Caddyfile with the official Caddy container image.

## v0.2.3

- Moved the GitHub Actions workflow to Node 24-based official actions to remove the Node 20 runtime deprecation warning.

## v0.2.2

- Made CI create the virtual environment expected by the test command, so clean runners verify the same workflow as local development.
- Made the private deployment environment path configurable for non-secret Compose validation.

## v0.2.1

- Hardened the public-release hygiene: portable deployment helpers, clean Markdown, and CI-ready privacy checks.

## v0.2.0

- Added individual accounts, Argon2id password hashes, hashed sessions, account-scoped conversations, login throttling, and account lockouts.
- Added Caddy-based HTTPS deployment, security headers, and public-source privacy boundaries.

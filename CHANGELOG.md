# Changelog

## Unreleased

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

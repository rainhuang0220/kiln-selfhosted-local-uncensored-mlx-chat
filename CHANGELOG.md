# Changelog

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

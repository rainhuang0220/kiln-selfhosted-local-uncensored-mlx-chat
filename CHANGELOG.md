# Changelog

## v0.2.2

- Made CI create the virtual environment expected by the test command, so clean runners verify the same workflow as local development.
- Made the private deployment environment path configurable for non-secret Compose validation.

## v0.2.1

- Hardened the public-release hygiene: portable deployment helpers, clean Markdown, and CI-ready privacy checks.

## v0.2.0

- Added individual accounts, Argon2id password hashes, hashed sessions, account-scoped conversations, login throttling, and account lockouts.
- Added Caddy-based HTTPS deployment, security headers, and public-source privacy boundaries.

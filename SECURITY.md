# Security policy

## Supported configuration

The current release line is supported when it runs behind the supplied Caddy TLS ingress with `COOKIE_SECURE=true`, `TRUST_PROXY_HEADERS=true`, a unique bootstrap password, and private runtime storage.

`deploy/.env`, SQLite files, TLS certificates, model weights, chat transcripts, and session records are runtime data. They must never be committed, uploaded to a public repository, or shared in an issue.

## Reporting a vulnerability

Please use GitHub's private security-advisory flow for this repository. Do not open a public issue for a suspected credential leak, authentication bypass, data exposure, or remote-code-execution vulnerability.

Include the affected release, a minimal reproduction, impact, and any safe mitigation you identified. We will acknowledge reports and coordinate a fix before disclosure.

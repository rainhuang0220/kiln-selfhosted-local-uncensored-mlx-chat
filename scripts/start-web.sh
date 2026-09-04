#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -d web/node_modules ]]; then
  echo "Missing web/node_modules — run: npm install --prefix web" >&2
  exit 1
fi
export VITE_API_TARGET="${VITE_API_TARGET:-http://127.0.0.1:8787}"
exec npm run dev --prefix web -- --host 127.0.0.1 --port 7777 --strictPort

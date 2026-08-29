#!/usr/bin/env bash
set -euo pipefail

blocked=0
while IFS= read -r -d '' path; do
  case "$path" in
    .env.example|*/.env.example|data/.gitkeep)
      ;;
    .env|.env.*|*/.env|*/.env.*|data/*|*.db|*.db-*|*.sqlite|*.sqlite3|*.pem|*.key|*.p12|*.pfx|secrets/*|*/secrets/*)
      printf 'refusing to publish sensitive path: %s\n' "$path" >&2
      blocked=1
      ;;
  esac
done < <(git ls-files -z)

if git grep -n -I -E -- '-----BEGIN( [A-Z0-9]+)? PRIVATE KEY-----|AKIA[0-9A-Z]{16}' -- .; then
  printf 'refusing to publish likely secret material\n' >&2
  blocked=1
fi

exit "$blocked"

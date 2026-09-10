#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
wrapper="$root/scripts/run-web-tunnel.sh"
installer="$root/scripts/install-web-tunnel.sh"

bash -n "$wrapper"
bash -n "$installer"

grep -q 'create_connection' "$wrapper"
grep -q 'remote listen disappeared' "$wrapper"
grep -q 'run-web-tunnel.sh' "$installer"
grep -q 'Application Support/kiln' "$installer"

# launchd must watch the health-checking wrapper, not a raw ssh that can zombie.
python3 - <<'PY'
from pathlib import Path
text = Path("scripts/install-web-tunnel.sh").read_text()
start = text.index("<key>ProgramArguments</key>")
end = text.index("</array>", start)
block = text[start:end]
if "/usr/bin/ssh" in block:
    raise SystemExit("installer still launches raw ssh as the LaunchAgent program")
if "run-web-tunnel.sh" not in block:
    raise SystemExit("installer LaunchAgent does not run run-web-tunnel.sh")
PY

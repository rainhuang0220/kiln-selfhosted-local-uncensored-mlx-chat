#!/usr/bin/env bash
# Install user LaunchAgents for the local Kiln UI (:7777) and API (:8787).
# Wrappers live under Application Support so launchd does not execute Desktop scripts.
# Does not replace com.kiln.mlx.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUPPORT="$HOME/Library/Application Support/kiln"
AGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
NODE="$(command -v node)"
NPM="$(command -v npm)"
NODE_DIR="$(dirname "$NODE")"
PATH_VALUE="${NODE_DIR}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
PY="$ROOT/.venv/bin/python"

mkdir -p "$SUPPORT" "$AGENTS"

cat > "$SUPPORT/start-api.sh" <<EOF
#!/bin/bash
set -euo pipefail
cd "$ROOT/backend"
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8787
EOF
chmod 755 "$SUPPORT/start-api.sh"

cat > "$SUPPORT/start-web.sh" <<EOF
#!/bin/bash
set -euo pipefail
export PATH="$PATH_VALUE"
export VITE_API_TARGET="http://127.0.0.1:8787"
cd "$ROOT"
exec "$NPM" run dev --prefix web -- --host 127.0.0.1 --port 7777 --strictPort
EOF
chmod 755 "$SUPPORT/start-web.sh"

write_plist() {
  local label="$1"
  local starter="$2"
  local log="$3"
  local plist="$AGENTS/${label}.plist"
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>${label}</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$SUPPORT/${starter}</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key><dict>
    <key>HOME</key><string>$HOME</string>
    <key>PATH</key><string>${PATH_VALUE}</string>
    <key>VITE_API_TARGET</key><string>http://127.0.0.1:8787</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>/tmp/${log}.log</string>
  <key>StandardErrorPath</key><string>/tmp/${log}.err</string>
</dict></plist>
EOF
  local domain="gui/${UID_NUM}/${label}"
  launchctl bootout "$domain" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/${UID_NUM}" "$plist"
  launchctl enable "$domain" >/dev/null 2>&1 || true
  launchctl kickstart -k "$domain"
  echo "installed $domain"
}

write_plist com.kiln.api start-api.sh kiln-api
sleep 1
write_plist com.kiln.web start-web.sh kiln-web
echo "UI  http://127.0.0.1:7777"
echo "API http://127.0.0.1:8787"
echo "logs: /tmp/kiln-api.log /tmp/kiln-web.log"

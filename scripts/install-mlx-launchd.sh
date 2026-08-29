#!/usr/bin/env bash
# Install a user LaunchAgent that starts this checkout's configurable mlx server.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUPPORT="$HOME/Library/Application Support/kiln"
AGENTS="$HOME/Library/LaunchAgents"
PLIST="$AGENTS/com.kiln.mlx.plist"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}/com.kiln.mlx"

mkdir -p "$SUPPORT" "$AGENTS"
cat > "$SUPPORT/start-mlx.sh" <<EOF
#!/usr/bin/env bash
exec "$ROOT/scripts/start-mlx.sh"
EOF
chmod 755 "$SUPPORT/start-mlx.sh"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.kiln.mlx</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$SUPPORT/start-mlx.sh</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key><dict><key>TOKENIZERS_PARALLELISM</key><string>false</string><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>/tmp/kiln-mlx.log</string>
  <key>StandardErrorPath</key><string>/tmp/kiln-mlx.err</string>
</dict></plist>
EOF

launchctl bootout "$DOMAIN" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID_NUM}" "$PLIST"
launchctl enable "$DOMAIN" >/dev/null 2>&1 || true
launchctl kickstart -k "$DOMAIN"
echo "installed $DOMAIN"
echo "logs: /tmp/kiln-mlx.log  /tmp/kiln-mlx.err"

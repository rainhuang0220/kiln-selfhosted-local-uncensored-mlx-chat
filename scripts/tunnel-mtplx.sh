#!/usr/bin/env bash
# Reverse-forward the local MLX server at 127.0.0.1:8081.
# onto the VPS loopback only. Does not publish the model port publicly.
set -euo pipefail
: "${KILN_SSH:?set KILN_SSH to the SSH destination, for example deploy@example.com}"
REMOTE="$KILN_SSH"
LOCAL_PORT="${MLX_PORT:-8081}"
REMOTE_PORT="${REMOTE_MLX_PORT:-8081}"
exec ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o BatchMode=yes \
  -R "127.0.0.1:${REMOTE_PORT}:127.0.0.1:${LOCAL_PORT}" \
  "$REMOTE"

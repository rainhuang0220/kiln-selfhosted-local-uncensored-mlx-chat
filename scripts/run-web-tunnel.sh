#!/usr/bin/env bash
# Reverse SSH: VPS 127.0.0.1:17777 -> this Mac 127.0.0.1:7777
# launchd KeepAlive restarts us. Exit if the VPS port is not actually listening —
# a local ssh process can stay ESTABLISHED through a TUN proxy after sshd is gone.
set -euo pipefail

REMOTE="${KILN_TUNNEL_REMOTE:-ubuntu@175.24.134.228}"
LISTEN="${KILN_TUNNEL_LISTEN:-127.0.0.1:17777}"
LOCAL="${KILN_TUNNEL_LOCAL:-127.0.0.1:7777}"
CONTROL="${KILN_TUNNEL_CONTROL:-/tmp/kiln-web-tunnel.sock}"
LISTEN_PORT="${LISTEN##*:}"

if [[ ! "$LISTEN_PORT" =~ ^[0-9]+$ ]]; then
  echo "invalid listen port in $LISTEN" >&2
  exit 1
fi

SSH_PID=""
cleanup() {
  if [[ -S "$CONTROL" ]]; then
    ssh -S "$CONTROL" -O exit "$REMOTE" >/dev/null 2>&1 || true
  fi
  if [[ -n "$SSH_PID" ]] && kill -0 "$SSH_PID" >/dev/null 2>&1; then
    kill "$SSH_PID" >/dev/null 2>&1 || true
    wait "$SSH_PID" 2>/dev/null || true
  fi
  rm -f "$CONTROL"
}
trap cleanup EXIT INT TERM

rm -f "$CONTROL"

ssh -M -S "$CONTROL" -N -T \
  -o ControlMaster=yes \
  -o ControlPersist=no \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=2 \
  -o BatchMode=yes \
  -o ConnectTimeout=15 \
  -R "${LISTEN}:${LOCAL}" \
  "$REMOTE" &
SSH_PID=$!

remote_listen_ok() {
  # Independent SSH on purpose: ControlMaster/-O check cannot see a TUN-zombied session.
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE" \
    "python3 -c \"import socket; s=socket.create_connection(('127.0.0.1', ${LISTEN_PORT}), 2); s.close()\"" \
    >/dev/null 2>&1
}

opened=0
for _ in $(seq 1 25); do
  if ! kill -0 "$SSH_PID" >/dev/null 2>&1; then
    wait "$SSH_PID" || true
    echo "ssh exited before remote ${LISTEN} opened" >&2
    exit 1
  fi
  if remote_listen_ok; then
    opened=1
    break
  fi
  sleep 1
done

if [[ "$opened" -ne 1 ]]; then
  echo "remote ${LISTEN} did not open" >&2
  exit 1
fi

echo "forward ${LISTEN} -> ${LOCAL} via ${REMOTE}"

while kill -0 "$SSH_PID" >/dev/null 2>&1; do
  sleep 15
  if ! remote_listen_ok; then
    echo "remote listen disappeared" >&2
    exit 1
  fi
done

wait "$SSH_PID" || true
echo "ssh child exited" >&2
exit 1

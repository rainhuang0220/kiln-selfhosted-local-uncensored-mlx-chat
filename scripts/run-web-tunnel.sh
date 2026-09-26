#!/usr/bin/env bash
# Reverse SSH: VPS 127.0.0.1:17777 -> this Mac 127.0.0.1:8787 (API).
# Vite on 127.0.0.1:7777 is local development only and must not be the public origin.
#
# Reliability model:
# - launchd KeepAlive restarts this script if it exits.
# - Inside the script: open one forward, monitor it, on loss reclaim stale remote
#   and reconnect with bounded exponential backoff + jitter (do NOT restart API/MLX).
# - Exit only when LOCAL API is down or route cannot be recovered (launchd then retries).
# - Never bind or expose MLX :8081.
set -euo pipefail

REMOTE="${KILN_TUNNEL_REMOTE:-kiln-tunnel@175.24.134.228}"
LISTEN="${KILN_TUNNEL_LISTEN:-127.0.0.1:17777}"
LOCAL="${KILN_TUNNEL_LOCAL:-127.0.0.1:8787}"
CONTROL="${KILN_TUNNEL_CONTROL:-/tmp/kiln-web-tunnel.sock}"
IDENTITY="${KILN_TUNNEL_IDENTITY:-$HOME/Library/Application Support/kiln/kiln-tunnel}"
ADMIN="${KILN_TUNNEL_ADMIN:-ubuntu@175.24.134.228}"
LISTEN_PORT="${LISTEN##*:}"
VPS_IP="${KILN_VPS_IP:-175.24.134.228}"
ROUTE_HELPER="${KILN_ROUTE_HELPER:-$HOME/Library/Application Support/kiln/ensure-vps-direct-route.sh}"
ROUTE_WAIT_S="${KILN_ROUTE_WAIT_S:-45}"
BACKOFF_BASE_S="${KILN_TUNNEL_BACKOFF_BASE_S:-2}"
BACKOFF_MAX_S="${KILN_TUNNEL_BACKOFF_MAX_S:-60}"
MAX_RECONNECT="${KILN_TUNNEL_MAX_RECONNECT:-40}"

emit() { echo "STATE=$1 $2" >&2; }

route_ready() {
  if [[ -f "$ROUTE_HELPER" ]]; then
    bash "$ROUTE_HELPER" --check
  else
    local vps_iface vps_gw
    vps_iface=$(/sbin/route -n get "$VPS_IP" 2>/dev/null | awk '/interface:/{print $2; exit}')
    vps_gw=$(/sbin/route -n get "$VPS_IP" 2>/dev/null | awk '/gateway:/{print $2; exit}')
    [[ "$vps_iface" != utun* && "$vps_gw" != 198.18.* ]] && netstat -rn -f inet | awk -v ip="$VPS_IP" '$1==ip && $3 ~ /H/ {found=1} END{exit !found}'
  fi
}

local_api_up() {
  python3 -c "import socket; s=socket.create_connection(('127.0.0.1', int('${LOCAL##*:}')), 2); s.close()" 2>/dev/null
}

tcp22_up() {
  python3 -c "import socket; s=socket.create_connection(('${VPS_IP}', 22), 3); s.close()" 2>/dev/null
}

wait_deps() {
  local waited=0
  while ! route_ready; do
    emit ROUTE_NOT_READY "waited=${waited}s vps=${VPS_IP}"
    if [[ "$waited" -ge "$ROUTE_WAIT_S" ]]; then
      emit ROUTE_NOT_READY "giving up after ${ROUTE_WAIT_S}s; refusing to open a zombie forward"
      return 1
    fi
    sleep 2
    waited=$((waited + 2))
  done
  if ! local_api_up; then
    emit LOCAL_TARGET_DOWN "nothing listening on ${LOCAL}"
    return 1
  fi
  if ! tcp22_up; then
    emit ROUTE_OK_TCP22_FAIL "UGHS route present but ${VPS_IP}:22 did not accept"
    return 1
  fi
  return 0
}

if [[ ! "$LISTEN_PORT" =~ ^[0-9]+$ ]]; then
  echo "invalid listen port in $LISTEN" >&2
  exit 1
fi

SSH_PID=""
cleanup_ssh() {
  if [[ -S "$CONTROL" ]]; then
    ssh -S "$CONTROL" -O exit "$REMOTE" >/dev/null 2>&1 || true
  fi
  if [[ -n "${SSH_PID}" ]] && kill -0 "$SSH_PID" >/dev/null 2>&1; then
    kill "$SSH_PID" >/dev/null 2>&1 || true
    wait "$SSH_PID" 2>/dev/null || true
  fi
  SSH_PID=""
  rm -f "$CONTROL"
}

on_exit() { cleanup_ssh; }
trap on_exit EXIT INT TERM

reclaim_stale_remote() {
  # After a roam the old sshd child can keep 17777, so the new -R fails.
  # Use ADMIN (shell-capable), not the tunnel-only user.
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$ADMIN" \
    "python3 -c \"
import os, signal, subprocess
try:
    out = subprocess.check_output(['lsof', '-nP', '-iTCP:${LISTEN_PORT}', '-sTCP:LISTEN'], text=True, stderr=subprocess.DEVNULL)
except Exception:
    raise SystemExit(0)
for line in out.splitlines()[1:]:
    parts = line.split()
    if len(parts) >= 2 and parts[0].startswith('sshd'):
        try:
            os.kill(int(parts[1]), signal.SIGTERM)
        except Exception:
            pass
\"" >/dev/null 2>&1 || true
  emit STALE_REMOTE_FORWARD "asked VPS to drop stale ${LISTEN} holder"
}

remote_listen_ok() {
  # Independent SSH on purpose: ControlMaster/-O check cannot see a TUN-zombied session.
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$ADMIN" \
    "python3 -c \"import socket; s=socket.create_connection(('127.0.0.1', ${LISTEN_PORT}), 2); s.close()\"" \
    >/dev/null 2>&1
}

jitter_sleep() {
  # Bounded exponential backoff with ±25% jitter. Args: attempt (0-based).
  local attempt="$1"
  local base="$BACKOFF_BASE_S"
  local max="$BACKOFF_MAX_S"
  local exp=$((base * (1 << (attempt > 5 ? 5 : attempt))))
  if [[ "$exp" -gt "$max" ]]; then exp=$max; fi
  local jitter
  jitter=$(python3 -c "import random; print(random.uniform(0.75, 1.25))" 2>/dev/null || echo 1)
  python3 -c "import time; time.sleep(max(1.0, ${exp} * ${jitter}))" 2>/dev/null || sleep "$exp"
}

start_forward() {
  cleanup_ssh
  SSH_ID=()
  if [[ -n "${IDENTITY}" && -f "${IDENTITY}" ]]; then
    SSH_ID=(-i "$IDENTITY" -o IdentitiesOnly=yes)
  fi
  ssh -M -S "$CONTROL" -N -T \
    "${SSH_ID[@]}" \
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

  local opened=0
  for _ in $(seq 1 25); do
    if ! kill -0 "$SSH_PID" >/dev/null 2>&1; then
      wait "$SSH_PID" || true
      emit SSH_CONNECT_FAILED "ssh exited before remote ${LISTEN} opened"
      reclaim_stale_remote
      return 1
    fi
    if remote_listen_ok; then
      opened=1
      break
    fi
    sleep 1
  done
  if [[ "$opened" -ne 1 ]]; then
    emit REMOTE_FORWARD_FAILED "remote ${LISTEN} did not open"
    reclaim_stale_remote
    cleanup_ssh
    return 1
  fi
  echo "forward ${LISTEN} -> ${LOCAL} via ${REMOTE}"
  return 0
}

monitor_forward() {
  while kill -0 "$SSH_PID" >/dev/null 2>&1; do
    sleep 15
    if ! local_api_up; then
      emit LOCAL_TARGET_DOWN "API ${LOCAL} disappeared during forward; exiting for launchd"
      return 2
    fi
    if ! remote_listen_ok; then
      emit REMOTE_LISTENER_LOST "remote listen disappeared"
      return 1
    fi
  done
  wait "$SSH_PID" || true
  emit SSH_CHILD_EXITED "ssh child exited"
  return 1
}

attempt=0
while [[ "$attempt" -lt "$MAX_RECONNECT" ]]; do
  if ! wait_deps; then
    # Dependency failure: exit so launchd retries; do not thrash reconnect without deps.
    exit 1
  fi
  if start_forward; then
    attempt=0
    mon=0
    monitor_forward || mon=$?
    cleanup_ssh
    if [[ "$mon" -eq 2 ]]; then
      exit 1
    fi
  fi
  emit RECONNECT_BACKOFF "attempt=${attempt} reclaim+backoff"
  reclaim_stale_remote
  jitter_sleep "$attempt"
  attempt=$((attempt + 1))
done

emit RECONNECT_EXHAUSTED "gave up after ${MAX_RECONNECT} reconnects; exiting for launchd"
exit 1

#!/usr/bin/env bash
# Restart mlx-lm only for the A/B/C/D prompt-cache experiment, then restore LaunchAgent.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/.venv/bin/python"
MODEL="/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4"
UID_NUM="$(id -u)"
LABEL="gui/${UID_NUM}/com.kiln.mlx"
PLIST="$HOME/Library/LaunchAgents/com.kiln.mlx.plist"
LOG="/tmp/kiln-mlx-experiment.log"
PIDFILE="/tmp/kiln-mlx-experiment.pid"
PROBE="$ROOT/benchmarks/dialogue_reliability/run_prompt_cache.py"

wait_ready() {
  local i
  for i in $(seq 1 90); do
    if curl -sf http://127.0.0.1:8081/v1/models >/dev/null; then
      echo "mlx ready after ${i} checks"
      return 0
    fi
    sleep 2
  done
  echo "mlx did not become ready" >&2
  tail -n 40 "$LOG" >&2 || true
  return 1
}

stop_all() {
  launchctl bootout "$LABEL" 2>/dev/null || true
  if [[ -f "$PIDFILE" ]]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
  pkill -f 'python -m mlx_lm.server' 2>/dev/null || true
  sleep 3
}

start_mlx() {
  : >"$LOG"
  "$PY" -m mlx_lm.server \
    --model "$MODEL" \
    --host 127.0.0.1 \
    --port 8081 \
    --max-tokens 32768 \
    --temp 0.7 \
    --top-p 0.8 \
    --top-k 20 \
    --decode-concurrency 1 \
    --prompt-concurrency 1 \
    --prefill-step-size 1024 \
    --prompt-cache-size 4 \
    --prompt-cache-bytes 4G \
    "$@" >>"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
  wait_ready
}

restore_launchagent() {
  stop_all
  launchctl bootstrap "gui/${UID_NUM}" "$PLIST" 2>/dev/null || launchctl load "$PLIST" 2>/dev/null || true
  wait_ready || true
}

trap restore_launchagent EXIT

echo "=== boot out LaunchAgent ==="
stop_all

echo "=== server: no --chat-template-args (cases A,B) ==="
start_mlx
"$PY" -u "$PROBE" \
  --server-label no-template-args \
  --cases A,B \
  --trials 3 \
  --turns 3 \
  --out "$ROOT/benchmarks/dialogue_reliability/runs/prompt-cache-AB.json"

echo "=== server: --chat-template-args enable_thinking=false (cases C,D + persist) ==="
stop_all
start_mlx --chat-template-args '{"enable_thinking":false}'
"$PY" -u "$PROBE" \
  --server-label template-false \
  --cases C,D,persist_stream,persist_nostream \
  --trials 3 \
  --turns 3 \
  --out "$ROOT/benchmarks/dialogue_reliability/runs/prompt-cache-CD.json"

echo "=== done; restoring LaunchAgent ==="

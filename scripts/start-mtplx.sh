#!/usr/bin/env bash
# OpenAI-compatible MTPLX server (native MTP). Default 4B hits >30 tok/s on M4 24GB.
# 9B is ~24 tok/s. 27B official MTPLX artifacts need ≥32 GB (Optimized Speed) or are a tight 20 GB peak (Bare Speed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MTPLX="${MTPLX_BIN:-$ROOT/../.mtplx-venv/bin/mtplx}"
CACHE="${MTPLX_CACHE:-$HOME/.mtplx/models}"
SIZE="${MTPLX_SIZE:-4b}"
PORT="${MTPLX_PORT:-8082}"
PROFILE="${MTPLX_PROFILE:-sustained}"
EXTRA=()

case "$SIZE" in
  4b|4B)
    REL="Youssofal--Qwen3.5-4B-MTPLX-Optimized-Speed"
    REPO="Youssofal/Qwen3.5-4B-MTPLX-Optimized-Speed"
    ;;
  9b|9B)
    REL="Youssofal--Qwen3.5-9B-MTPLX-Optimized-Speed"
    REPO="Youssofal/Qwen3.5-9B-MTPLX-Optimized-Speed"
    ;;
  *)
    echo "MTPLX_SIZE must be 4b or 9b (got $SIZE). Uncensored 9B is mlx-lm HauhauCS, not MTPLX." >&2
    exit 1
    ;;
esac

MODEL="$CACHE/$REL"
if [[ ! -x "$MTPLX" ]]; then
  echo "Missing $MTPLX — create with: /opt/homebrew/bin/python3.12 -m venv $ROOT/../.mtplx-venv && $ROOT/../.mtplx-venv/bin/pip install mtplx" >&2
  exit 1
fi
if [[ ! -f "$MODEL/mtplx_runtime.json" ]]; then
  echo "Missing $MODEL — download with: $MTPLX pull $REPO" >&2
  exit 1
fi

exec "$MTPLX" serve \
  --model "$MODEL" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --profile "$PROFILE" \
  --no-auth \
  --no-stats-footer \
  --warmup-tokens 32 \
  --yes \
  "${EXTRA[@]}"

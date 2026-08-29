#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Public 8081 default: HauhauCS Aggressive 9B mxfp4. Local 27B: MODEL_PATH=$ROOT/../qwen3.8-27b
MODEL="${MODEL_PATH:-$ROOT/../qwen3.5-9b-hauhau-aggressive-mxfp4}"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing $PY — recreate with: uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python mlx mlx-lm -e './backend[dev]'" >&2
  exit 1
fi
ver="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$ver" != "3.12" && "$ver" != "3.11" && "$ver" != "3.13" ]]; then
  echo "mlx-lm is unstable on Python $ver (crashes via duplicate OpenMP on 3.14). Use 3.12." >&2
  exit 1
fi
export TOKENIZERS_PARALLELISM=false
exec "$PY" -m mlx_lm.server \
  --model "$MODEL" \
  --host 127.0.0.1 \
  --port 8081 \
  --max-tokens 32768 \
  --temp 1.0 \
  --top-p 0.95 \
  --top-k 20 \
  --decode-concurrency 1 \
  --prompt-concurrency 1 \
  --prefill-step-size 1024 \
  --prompt-cache-size 4 \
  --prompt-cache-bytes 4G \
  --chat-template-args '{"enable_thinking":true,"reasoning_effort":"medium"}'

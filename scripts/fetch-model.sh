#!/usr/bin/env bash
set -euo pipefail

REPO="TheCluster/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-MLX-mxfp4"
REVISION="a9e5f6d9aebfe8bae436bdd51da14dde5b1b30c9"
DESTINATION="${MODEL_DIR:-$(cd "$(dirname "$0")/../.." && pwd)/qwen3.5-9b-hauhau-aggressive-mxfp4}"
FILES="model-00001-of-00002.safetensors,model-00002-of-00002.safetensors"

if [[ "${1:-}" == "--dry-run" ]]; then
  printf 'repo=%s\nrevision=%s\nfiles=%s\ndestination=%s\n' "$REPO" "$REVISION" "$FILES" "$DESTINATION"
  exit 0
fi

if ! command -v hf >/dev/null; then
  echo 'Missing Hugging Face CLI. Install it with: pip install -U huggingface_hub' >&2
  exit 1
fi

hf download "$REPO" --revision "$REVISION" --local-dir "$DESTINATION"
(
  cd "$DESTINATION"
  printf '%s  %s\n' \
    '3c6a3cf82f972bdd7ff1c4d8f4a0ccfc90d99c1a962736b05a4015bdce83b8ab' \
    'model-00001-of-00002.safetensors' \
    | shasum -a 256 --check
  printf '%s  %s\n' \
    'dade3cb3720af9d71bf82e7925e61c7533a365906bdac635e6e4206fe1d1e0aa' \
    'model-00002-of-00002.safetensors' \
    | shasum -a 256 --check
)

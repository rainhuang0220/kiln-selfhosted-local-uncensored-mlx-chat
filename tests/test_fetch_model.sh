#!/usr/bin/env bash
set -euo pipefail

output="$(bash scripts/fetch-model.sh --dry-run)"
grep -Fqx 'repo=TheCluster/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-MLX-mxfp4' <<<"$output"
grep -Fqx 'revision=a9e5f6d9aebfe8bae436bdd51da14dde5b1b30c9' <<<"$output"
grep -Fqx 'files=model-00001-of-00002.safetensors,model-00002-of-00002.safetensors' <<<"$output"

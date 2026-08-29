# Models

Kiln is model-flexible: it talks to an OpenAI-compatible local inference server and does not bundle model weights. `MODEL_PATH` selects the checkpoint used by `npm run start:mlx`.

## Verified default: Qwen3.5-9B Uncensored Aggressive MLX mxfp4

The maintained profile is [`TheCluster/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-MLX-mxfp4`](https://huggingface.co/TheCluster/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-MLX-mxfp4), pinned to revision `a9e5f6d9aebfe8bae436bdd51da14dde5b1b30c9`.

```bash
pip install -U huggingface_hub
npm run fetch:model
npm run start:mlx
```

The downloader fetches the pinned revision and verifies both weight shards with SHA-256. The upstream Hauhau model card lists Apache-2.0; retain its attribution and review both model cards before redistribution.

## Switch models

Point `MODEL_PATH` at a compatible local MLX checkpoint before starting the server:

```bash
MODEL_PATH=/path/to/another-mlx-model npm run start:mlx
```

Choose a matching `MODEL_NAME` in `.env` when you want API metadata to identify the alternative model. Kiln does not claim that every checkpoint behaves identically; context limits, tokenizer availability, speed, and safety behavior are model-specific.

## Larger 27B profile

The repository retains historical documentation and benchmarks for a Qwen3.8-27B 4-bit MLX profile. It is a useful Apple Silicon performance reference, but it is not downloaded, mounted, or required by the default deployment.

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

## Model Workbench (recommended)

Open **Model library** in the sidebar (or **Models** in the chat header). Kiln searches the live Hugging Face catalogue without sending your conversations or filesystem paths to the Hub. Each result opens the upstream model card in a new tab.

Only repositories marked **MLX-ready** can be installed directly: the server checks this again before a job is created. A completed download is stored under `MODEL_LIBRARY_PATH` (default: `../models`, outside this repository), with its provenance in a local `kiln-model.json`. **Download + use** writes the active selection under private runtime data, restarts the Mac LaunchAgent, and preserves the choice across API restarts.

The public deployment profile is deliberately read-only: it cannot download or switch models from the Internet-facing API. Keep model management on the private Apple Silicon host.

## Switch models manually

Point `MODEL_PATH` at a compatible local MLX checkpoint before starting the server:

```bash
MODEL_PATH=/path/to/another-mlx-model npm run start:mlx
```

Choose a matching `MODEL_NAME` in `.env` when you want API metadata to identify the alternative model. Kiln does not claim that every checkpoint behaves identically; context limits, tokenizer availability, speed, and safety behavior are model-specific.

## Larger 27B profile

The repository retains historical documentation and benchmarks for a Qwen3.8-27B 4-bit MLX profile. It is a useful Apple Silicon performance reference, but it is not downloaded, mounted, or required by the default deployment. This release does not add a Chat Quality toggle for 27B: swapping it would take down the live 9B worker, and no offline A/B on this host justified the extra product surface.

## Filters vs checkpoints

Kiln does not apply an application-layer safety filter on Chat, Image, or Video. That is not the same as “the model has no learned safety bias.”

| Path | Checkpoint | Provenance | Censorship claim |
| --- | --- | --- | --- |
| Chat | HauhauCS Qwen3.5-9B Aggressive MLX mxfp4, revision `a9e5f6d9…` | Verified against the pinned Hub card | Upstream card claims refusal removal (`0/465`). Kiln does not re-run that suite. |
| Image Fast | Tongyi-MAI Z-Image-Turbo via mflux 4-bit | Standard upstream | **Not claimed uncensored.** |
| Image Quality | black-forest-labs/FLUX.1-dev via mflux 4-bit (local pack `image-flux1-dev-mflux-4bit`) | Standard upstream, Non-Commercial License | **Not claimed uncensored.** Chat parks during Quality. Measured ~10–12 min / 1024² / 20 steps. Better exact count than Z-Image; still misses jump-onto-table. |
| Image leftover | FLUX.2 Klein 4B | Standard upstream | Official text encoder may sanitize prompts. |
| Video | `wan_1.3B_exp_e14` fine-tune of Wan-AI/Wan2.1-T2V-1.3B | Card in `video-nsfw-wan-1.3b/README.md` | NSFW fine-tune claimed by the trainer. Directory name is not the evidence. Runtime still applies Wan’s default **quality** negative prompt (oversaturation / artifacts / extra fingers), not an NSFW blocklist. T5 `text_len` is 512 tokens. |

Do not write “Kiln is fully uncensored.”

# Local generation backends (M4 24GB)

Chat remains Hauhau Qwen3.5-9B on `:8081`. Image and video workers load on demand and do not overwrite that checkpoint.

## Image

| Backend | Role |
| --- | --- |
| Z-Image Turbo, mflux 4-bit | Default. Unfiltered generation on the tested prompts. |
| FLUX.2 Klein 4B | Optional faster path. Official text encoder may silently sanitize prompts. |

## Video

| Backend | Role |
| --- | --- |
| Wan 1.3B MLX 4-bit | Default. T5 bfloat16 + TeaCache 0.05. Standard 17 frames ≈ 210 s. |

Longer clips (49+ frames) and native 720p are possible but not recommended defaults on 24GB. Optional 720p output is ffmpeg lanczos after 480p generation.

See `benchmarks/video/summary.json`.

# Next models after capacity bottleneck

```
PRIMARY: FLUX.1-dev Q4 via mflux (`flux1-dev`)
BACKUP: Qwen-Image-2512 Q4 via mflux (`mflux-generate-qwen -q 4 --low-ram`)
DO_NOT_DOWNLOAD: FLUX.2-dev, Qwen-Image BF16, Wan 5B/14B, Chat 27B on :8081
```

Measured on this machine: Z-Image Turbo Q4 still misses exact count after a correct Effective Prompt; Wan 1.3B still misses walk-then-sit after Fast and Quality. This note is the Image Quality decision. Nothing extra was downloaded beyond the primary pack.

## Decision

**Ship Image Fast = Z-Image Turbo Q4 (default). Ship Image Quality = FLUX.1 [dev] Q4 (opt-in).**

Real 4-prompt A/B, seed 42, Enhanced:

| | overall | count | spatial | action | extras |
| --- | --- | --- | --- | --- | --- |
| Z-Image Enhanced | 81.3% | 50% | 100% | 50% | saucer invented |
| FLUX.1-dev Enhanced | 87.5% | 100% | 100% | 0% | no saucer; four lemons |

FLUX wins the exact-count miss that defined the Z-Image bottleneck. It does **not** win action landing (cat walks, does not jump onto the table). Quality is shipped as an opt-in, not because it is universally more obedient. Fast stays the default so public chat is not parked for 10–12 minutes.

Qwen-Image-2512 remains the unused backup (20B + 7B encoder, ~58GB BF16 snapshot). Do not download it this turn. Action landing still needs a stronger model later.

## Constraint

- Apple M4, 24GB unified memory
- MLX / mflux already in `.media-venv`
- Chat Qwen3.5-9B stays on `:8081` except while Quality parks
- Prompt adherence over speed
- One new weight tree only

## Image Quality: FLUX.1 [dev] Q4

- Params: 12B ([BFL card](https://huggingface.co/black-forest-labs/FLUX.1-dev))
- Runtime: `mflux-generate --model <local> --base-model dev --low-ram --vae-tiling --steps 20 --guidance 3.5`
- Quant: 4-bit. mflux documents ~9.61GB for 4-bit FLUX.1 ([historical mflux table](https://pypi.org/project/mflux/0.6.1/)); community 4-bit pack is 9,612,501,971 bytes ([AITRADER/FLUX1-dev-mlx-4bit](https://huggingface.co/AITRADER/FLUX1-dev-mlx-4bit))
- Working set: ~9GB weights + activations. Chat parks so 9B mxfp4 does not share the 24GB during the job.
- Speed: slower than Z-Image Turbo 9-step; typically several minutes at 1024² / 20 steps
- License: FLUX.1 [dev] Non-Commercial License
- Provenance: official BFL weights, MLX via mflux; local directory `../image-flux1-dev-mflux-4bit`
- Adherence: first-party BFL card, “Competitive prompt following.” Not a turbo distill.
- EN/ZH: English-native T5/CLIP encoders. Chinese prompts still go through Kiln Enhanced / Translate+Enhance.
- Safety layer: no Kiln application filter. Not claimed uncensored.
- Integration: same job / inspector / Raw-Enhanced path as Z-Image.

## Backup: Qwen-Image-2512 Q4

- Params: 20B + 7B VL encoder ([arxiv 2508.02324](https://arxiv.org/abs/2508.02324))
- Runtime: `mflux-generate-qwen -q 4 --low-ram`
- Why not primary: 58GB BF16 snapshot; 24GB OOM risk; first run would contend with public chat
- Why it remains backup: multilingual / Chinese-native encoder, first-party “strong prompt understanding”

## Video

Unchanged. LTX-2.3 int4 remains the only later video candidate worth a dedicated turn. Do not download it here.

## Sources

1. https://github.com/filipstrand/mflux
2. https://huggingface.co/black-forest-labs/FLUX.1-dev
3. https://huggingface.co/AITRADER/FLUX1-dev-mlx-4bit
4. https://github.com/filipstrand/mflux/blob/main/src/mflux/models/qwen/README.md
5. https://huggingface.co/Qwen/Qwen-Image-2512
6. https://arxiv.org/abs/2508.02324

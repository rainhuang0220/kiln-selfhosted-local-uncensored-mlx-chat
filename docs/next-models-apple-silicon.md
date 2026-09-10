# Next models after capacity bottleneck

Measured on this machine: Z-Image Turbo Q4 still misses exact count after a correct Effective Prompt; Wan 1.3B still misses walk-then-sit after Fast and Quality. This note lists replacements that can actually run on the current Mac. Nothing here was downloaded.

## Constraint

- Apple M4, 24GB unified memory
- MLX / mflux / otherwise native Apple Silicon
- Quality and prompt adherence over speed
- No download in this turn

## Image candidates (max 3)

### 1. Qwen-Image-2512 via mflux (`mflux-generate-qwen`)

- Params: 20B MMDiT + Qwen2.5-VL 7B text encoder ([mflux Qwen README](https://github.com/filipstrand/mflux/blob/main/src/mflux/models/qwen/README.md), [Qwen-Image report](https://arxiv.org/abs/2508.02324))
- Quant that can be tried on 24GB: mflux `-q 8` is the documented example; 4/6-bit exist. mflux warns 6-bit and below degrade more than Flux.
- Working-set RAM: UNKNOWN. Full BF16 snapshot on Hugging Face is ~58GB (`usedStorage` 57,699,806,247 bytes on [Qwen/Qwen-Image-2512](https://huggingface.co/Qwen/Qwen-Image-2512)). Must be quantized; peak unified-memory use on M4 is unpublished.
- Runtime: mflux, command `mflux-generate-qwen`. Official weights id `Qwen/Qwen-Image-2512`.
- License: Apache 2.0
- Provenance: [Qwen/Qwen-Image-2512](https://huggingface.co/Qwen/Qwen-Image-2512)
- Adherence evidence: official card claims better semantic instruction following than the August Qwen-Image (example: “body leaning slightly forward”). mflux describes the family as “strong prompt understanding” and bilingual (EN/ZH).
- Why it might beat Z-Image Turbo on count/spatial/action: larger MMDiT + a 7B vision-language encoder, Chinese-native, not an 8-step turbo distill.
- Risk: 20B+7B on 24GB may OOM even at 8-bit; first run will be slow; no local A/B yet.

### 2. FLUX.1 [dev] via mflux (`mflux-generate --model dev`)

- Params: 12B
- Quant: mflux `--quantize 8` or `4` (documented in [mflux FLUX README](https://github.com/filipstrand/mflux/blob/main/src/mflux/models/flux/README.md))
- Working-set RAM: UNKNOWN on this M4. 12B Q4 weights are the usual ~6–8GB class; peak Metal working set is unpublished here.
- Runtime: mflux (already in the image worker)
- License: FLUX.1 [dev] Non-Commercial License ([black-forest-labs/FLUX.1-dev](https://huggingface.co/black-forest-labs/FLUX.1-dev))
- Provenance: official BFL weights, MLX port by filipstrand/mflux
- Adherence evidence: BFL card, “Competitive prompt following, matching the performance of closed source alternatives.”
- Why it might beat Z-Image Turbo: 12B non-turbo prior, long local track record for composition. Not a speed distill.
- Risk: non-commercial license; official card also says the model may fail to match prompts. Slower than Z-Image Turbo.

### 3. Keep Z-Image Turbo Q4 as the control, not a third download

A third “bigger is better” name (FLUX.2-dev, HiDream-I1) does not have a published M4-24GB working set that fits. Do not add a third image checkpoint until Qwen-Image-2512 Q4/Q8 actually loads.

## Video candidates (max 3)

### 1. LTX-2.3 MLX int4

- Params: LTX-2.3 is a 22B family (HF `base_model: Lightricks/LTX-2.3`)
- Quant: int4 pack
- Working set: official port table says pack size ~12GB, RAM 16GB+ ([dgrauet/ltx-2-mlx](https://github.com/dgrauet/ltx-2-mlx))
- Runtime: `ltx-2-mlx` on Apple Silicon / Metal
- License: weights `ltx-2-community-license-agreement`; port MIT
- Provenance: [dgrauet/ltx-2.3-mlx-q4](https://huggingface.co/dgrauet/ltx-2.3-mlx-q4), converted by mlx-forge
- Adherence evidence: first-party **Prompt Relay** (`--segment`) gates prompt tokens onto timeline slices. That is the only local feature aimed at walk-then-sit style constraints.
- Why it might beat Wan 1.3B: 22B vs 1.3B, plus explicit temporal prompt segments. Slow is acceptable.
- Risk: 24GB is above the 16GB int4 floor but below the 32GB int8 recommendation. Two-stage / 97-frame defaults may still OOM. Gemma text encoder can collide with chat `:8081` the same way Wan parks chat. Sequential-action quality is unproven on this machine.

### 2. There is no second 24GB video upgrade worth downloading yet

Wan 2.2 TI2V-5B and Wan 14B / Hunyuan 13B do not have a first-party MLX path that fits 24GB with headroom. Do not raise Wan 1.3B steps past Quality (20). Keep the current Wan Fast/Quality pair as the control if LTX is tried.

## Not recommended on 24GB

- FLUX.2-dev GGUF Q4: community M3 Pro peak ~29GB unified memory
- LTX-2.3 MLX int8: table says ~21GB pack / 32GB+ RAM
- LTX-2.3 MLX bf16: ~42GB / 64GB+
- Wan 2.2 5B q8: previously measured ~18GB pack, 32GB+ recommended
- Chat 27B on `:8081` during any of the above: will evict the public chat worker

## Sources

1. https://github.com/filipstrand/mflux
2. https://github.com/filipstrand/mflux/blob/main/src/mflux/models/qwen/README.md
3. https://huggingface.co/Qwen/Qwen-Image-2512
4. https://arxiv.org/abs/2508.02324
5. https://huggingface.co/black-forest-labs/FLUX.1-dev
6. https://github.com/filipstrand/mflux/blob/main/src/mflux/models/flux/README.md
7. https://github.com/dgrauet/ltx-2-mlx
8. https://huggingface.co/dgrauet/ltx-2.3-mlx-q4

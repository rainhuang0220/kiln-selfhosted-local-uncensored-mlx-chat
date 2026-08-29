# Kiln inference benchmarks

Hardware: Apple M4, 24 GB unified memory.
Model: Qwen3.8-27B 4-bit MLX (`qwen3.8-27b`).
Server: `mlx_lm.server` via Python 3.12 venv, `127.0.0.1:8081`.

Harness: `benchmarks/run_inference.py` (HTTP SSE, does **not** load a second copy of the weights).

```bash
cd kiln
.venv/bin/python benchmarks/run_inference.py --cases A --out benchmarks/baseline/baseline.json
# optional, heavier:
.venv/bin/python benchmarks/run_inference.py --cases B --out benchmarks/inference/b.json
```

Cases:

| Case | Prompt tokens | max_tokens |
|---|---:|---:|
| A | 100 | 100 |
| B | 1_000 | 200 |
| C | 4_000 | 200 |
| D | 8_000 | 200 |

D can OOM on 24 GB. Do not run C/D while the UI is also generating.

Streaming is UX only. Decode tok/s is `completion_tokens / (total_s - ttft_s)`.

## Baseline A (thinking off, 2026-08-23)

Recorded in `benchmarks/baseline/baseline.json`:

| Metric | Value |
|---|---|
| prompt_tokens | 112 |
| completion_tokens | 100 |
| TTFT | 19.44 s (includes Metal warmup / prefill) |
| decode | **4.88 tok/s** |
| total | 39.94 s |
| cached_tokens | 0 (first request) |
| process RSS | ~170–225 MB (**does not include Metal wired memory**; weights ~14 GB live in unified memory) |

User-reported ~6.5 tok/s is the same order of magnitude after warmup. Do not treat streaming as a speedup.

Second identical A (`benchmarks/cache/a_second.json`): `cached_tokens=111` of `prompt_tokens=112` — mlx LRU prefix cache **does** fire across HTTP requests. Decode **7.10 tok/s**. TTFT still noisy (queue/warmup); use `cached_tokens` not wall TTFT as the cache metric.

Optimization log:

| Change | Expected | Measured |
|---|---|---|
| Python 3.14 → 3.12 | stop OpenMP abort | import + server stay up |
| decode-concurrency 1 | avoid 27B batch blowup | (server flag) |
| prompt LRU (mlx built-in) | lower TTFT on turn 2+ | `cached_tokens` on usage |
| thinking default medium | avoid xhigh empty-content | qualitative |
| KV INT8 on server | n/a | **not exposed** in 0.31.3 server |
| speculative decoding | n/a | **impossible on this checkpoint** — `ArraysCache` is not trimmable (`ValueError` in 0.31.3) |
| `--prompt-cache-size 10` → `3` + `1G` | avoid cloning 10 hybrid caches in 3.7 GiB leftover | **landed** in `scripts/start-mlx.sh`; live A2/A3 `cached_tokens=108/112`, TTFT 2.67s → 0.74s |
| `--prefill-step-size 512` | lower prefill activation spike vs 2048 | **landed**; 1k-prompt prefill **62 tok/s** |

Those flags stabilize 24GB and TTFT. They do **not** move decode off the memory-bandwidth wall.

## Live (same 27B, flags on, 2026-08-23 ~01:55)

`benchmarks/live/mlx_lm_now.json`. Warmup then 3× case A + 1× case B, thinking off.

| | Prefill (encode) | Decode | TTFT |
|---|---:|---:|---:|
| A (112 in / 100 out), mean of 3 | 42 tok/s cold; cache-hit TTFT 0.74s | **6.63 tok/s** (6.58–6.67) | 2.67s cold / 0.74s cached |
| B (1012 in / 100 out) | **62.1 tok/s** | **6.61 tok/s** | 16.3s |

**Average decode is ~6.6 tok/s. Not 30.**

## Why 30 tok/s is not this 27B on this Mac

M4 unified bandwidth is ~120 GB/s. This checkpoint is **14.09 GiB** and has **zero `mtp.*` tensors** (`mtplx inspect`: `native-ar-only-missing-mtp`). One AR token reads ~the whole trunk → ceiling ~8–9 tok/s. mlx-lm 0.31.3 also drops MTP on load. Speculative decoding still raises `ArraysCache` is not trimmable.

[MTPLX](https://github.com/youssofal/MTPLX) is real (native MTP, no extra drafter). It **cannot accelerate this AEON folder**. Official 27B Optimized Speed peaks at **25 GiB** (needs 32GB+). Bare Speed peaks ~20 GiB (tight on 24GB) and is a different, censored Qwen trunk.

Measured on this M4 24GB with MTPLX 2.9.1 (same night):

| Runtime | Model | Prefill | Decode (A, mean of 3) | ≥30? |
|---|---|---:|---:|---|
| mlx-lm 0.31.3 | AEON 27B 4bit (this tree) | 62 tok/s @1k | **6.63** | no |
| MTPLX sustained D2 | Qwen3.5-9B Optimized Speed | 171 tok/s | **24.2** | no |
| MTPLX turbo D2 | same 9B | 170 tok/s | **23.9** | no (6-bit skips compiled verify) |
| MTPLX turbo D3 | Qwen3.5-4B Optimized Speed | **327 tok/s** | **52.1** | **yes** |

4B also did 48.6 decode / 397 prefill on case B (1012-in). Artifacts: `benchmarks/live/mtplx_9b_now.json`, `mtplx_9b_turbo.json`, `mtplx_4b_turbo.json`.

To serve the 30 tok/s path (replaces 27B quality with 4B):

```bash
npm run start:mtplx          # 127.0.0.1:8082, default 4B turbo
MTPLX_SIZE=9b npm run start:mtplx
# point Kiln at it:
MLX_BASE_URL=http://127.0.0.1:8082 npm run dev
```

Do not load 27B mlx-lm and MTPLX at the same time on 24GB.

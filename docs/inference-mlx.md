# mlx-lm 0.31.3 inference notes (Kiln / Qwen3.8-27B)

What `mlx_lm.server` actually does on this machine versus `mlx_lm.generate` /
`mlx_lm.cache_prompt`. Read this before claiming a speedup.

Checked against **mlx-lm 0.31.3** in both:

- `/opt/homebrew/lib/python3.14/site-packages/mlx_lm` (identical sources)
- the project's Python 3.12 virtual environment (`.venv/.../site-packages/mlx_lm`)

Kiln’s process is the venv one (`scripts/start-mlx.sh`). Python 3.14 is not used
to serve: mlx-lm is unstable there (duplicate OpenMP). The two trees are the
same version.

Hardware used for the numbers below (live `mx.device_info()`):

| | |
|---|---|
| Chip | Apple M4 |
| Unified memory | 24 GiB (`memory_size` = 25 769 803 776) |
| Metal recommended working set | **17.76 GiB** (`max_recommended_working_set_size` = 19 069 665 280) |
| Max single Metal buffer | 13.32 GiB |

Checkpoint: `../qwen3.8-27b`

| | |
|---|---|
| Weights | 15 133 043 513 bytes ≈ **14.09 GiB** (4-bit affine, group 64) |
| `model_type` | `qwen3_5` (`Qwen3_5ForConditionalGeneration`) |
| Layers | 64, `full_attention_interval=4` → **48 linear / GatedDeltaNet + 16 full attention** |
| Vocab | 248 320 (not Qwen3’s 151 936) |
| Config `mtp_num_hidden_layers` | 1, but mlx-lm **drops** `mtp.*` weights in `sanitize()` |

This is a **hybrid** model. Linear layers use `ArraysCache` (conv + recurrent
state, O(1) in sequence length, **not trimmable**). Full-attention layers use
`KVCache` (grows with tokens, trimmable, quantizable). Speculative decoding
and “trim a longer cache down to a shared prefix” require **every** layer to be
trimmable. That is the constraint everything else hangs on.

---

## Verdict table

| Feature | `mlx_lm.server` (HTTP, what Kiln uses) | CLI only (`generate` / `cache_prompt` / `chat`) |
|---|---|---|
| OpenAI `/v1/chat/completions` + `/v1/completions` | Yes | n/a |
| Process-global `LRUPromptCache`, prefix reuse **across HTTP requests** | **Yes** (with hybrid caveats below) | n/a (generate is one-shot; `chat` keeps one in-process cache) |
| `usage.prompt_tokens_details.cached_tokens` | **Yes** | No HTTP usage object |
| `--prompt-cache-size` / `--prompt-cache-bytes` | Yes (Kiln: size 3, 1G) | No |
| `--decode-concurrency` / `--prompt-concurrency` | Yes | No |
| `--draft-model` / `--num-draft-tokens` | Flag **exists**; **crashes** on this model | Flag exists; **same crash** |
| HTTP body `draft_model` / `num_draft_tokens` | Parsed; same crash if a draft is loaded | n/a |
| `--kv-bits` / `--kv-group-size` / `--quantized-kv-start` | **Absent** | `generate` and `cache_prompt` only |
| `--max-kv-size` (rotating KV) | **Absent**; ignored anyway because the model implements `make_cache()` | `generate` / `chat` |
| `--prompt-cache-file` (safetensors dump) | **Absent** | `cache_prompt` write + `generate` read |
| Internal MTP as a drafter (`qwen3_5_mtp`) | Not registered; MTP weights stripped | Same |
| Thinking via `--chat-template-args` | Yes (Kiln already sets this) | `generate --chat-template-config` |

---

## 1. `LRUPromptCache` — does it reuse a prefix across HTTP requests?

**Yes.** The HTTP process builds one `LRUPromptCache` at startup and keeps it
for the life of the process. It is not per-request and not per-connection.

```1742:1744:/opt/homebrew/lib/python3.14/site-packages/mlx_lm/server.py
    prompt_cache = LRUPromptCache(model_provider.cli_args.prompt_cache_size)
    response_generator = ResponseGenerator(model_provider, prompt_cache)
```

`--prompt-cache-size` is “max number of **distinct stored sequences**”, default
10, already set in `scripts/start-mlx.sh`. `--prompt-cache-bytes` (optional)
caps total tensor bytes; Kiln does not set it.

### How a hit is decided

`fetch_nearest_cache` walks a token trie (`PromptTrie.search`) and then:

1. **Exact** sequence already stored → deepcopy that cache, `rest = []`.
2. **Longer** stored sequence that *starts with* the new prompt → deepcopy +
   **trim** the extra suffix, but **only if** `can_trim_prompt_cache(...)` is
   true for **all** layers.
3. **Shorter** stored sequence that is a prefix of the new prompt → deepcopy,
   `rest = tokens[len(prefix):]`. **No trim.** This is the hybrid-safe path.
4. Else miss → fresh `make_cache()`, prefill the whole prompt.

Qwen3.5 `make_cache()`:

```304:305:/opt/homebrew/lib/python3.14/site-packages/mlx_lm/models/qwen3_5.py
    def make_cache(self):
        return [ArraysCache(size=2) if l.is_linear else KVCache() for l in self.layers]
```

`ArraysCache` does **not** override `is_trimmable()`. It inherits
`_BaseCache.is_trimmable() → False`. So path (2) never runs for this checkpoint.
Path (3) does.

Maintainers confirmed this for Qwen3.5: sequential multi-turn hits the shorter
prefix; **forked** prompts that share a system prompt but diverge at the first
user turn cannot trim a longer entry. mlx-lm 0.31.3’s **batch** path mitigates
the common case by checkpointing at segment boundaries (system / user /
thinking tail) so a *shorter* system or user snapshot exists without trim
([ml-explore/mlx-lm#980](https://github.com/ml-explore/mlx-lm/issues/980),
closed as “reuse works for continuing a conversation”; hybrid trim still
impossible).

This checkpoint **is** batchable (`ArraysCache.merge` exists, no draft model),
so Kiln’s server uses `BatchGenerator` even with `--decode-concurrency 1`.
That is the path that writes those segment snapshots.

### What a hit looks like for Kiln

Kiln always POSTs the full `messages[]`. The server has no conversation store.

Kiln’s default is `preserve_thinking: false`. The next-turn template therefore
**omits** `<think>…</think>` / `reasoning_content`. The KV stored after turn 1
includes those tokens; turn 2’s token stream does not. Shared prefix is
roughly **system + previous user (+ assistant header)**, not the previous
completion. Prefill still runs over the last answer + the new user text. That
is expected, not a broken cache.

A **stable system prompt** across conversations is worth a cache entry: after
the first request, a later new chat with the same system can hit the stored
system segment. Changing `enable_thinking` / `reasoning_effort` / tools JSON
retokenizes the prefix and misses.

`decode-concurrency 1` does **not** disable the LRU. It only sets the
continuous-batch decode width to 1, which is what we want on 24 GB.

### How to measure `cached_tokens`

The server copies the hit length into `GenerationContext.prompt_cache_count`
(`len(full_prompt) - len(rest)`).

**Non-stream** completions always emit it:

```json
"usage": {
  "prompt_tokens": 1200,
  "completion_tokens": 80,
  "total_tokens": 1280,
  "prompt_tokens_details": { "cached_tokens": 950 }
}
```

(`prompt_tokens` is the **full** tokenized prompt, not the uncached tail.)

**Stream** completions omit `usage` on token chunks. It is attached only when
the client sends `stream_options: { "include_usage": true }` (Kiln already
does). Then a **final usage-only event** (`choices: []`) carries the same
`prompt_tokens_details.cached_tokens`. Intermediate deltas have no cache
field — treating a missing field as 0 until that event is correct.

Kiln mapping: `backend/app/providers/mlx.py` reads
`usage.prompt_tokens_details.cached_tokens`.

**Do not** use SSE `: keepalive processed/total` as the cache metric. That
callback is over the **uncached tail** (`rest`), so a good hit looks like a
short prefill, not like `processed == prompt_tokens`.

Server logs (INFO) on each generate:

```text
Prompt Cache: N sequences, X.XX GB
- assistant: …
- user: …
- system: …
```

A real hit: `cached_tokens > 0` **and** TTFT drops versus a cold prompt of the
same length. `cached_tokens == prompt_tokens` is rare in chat (that would be
an exact replay of a stored sequence). `cached_tokens == 0` on turn 2 of the
same conversation, same system, same template kwargs, is a miss worth
debugging (template drift, truncated history, or LRU eviction).

### RAM cost of `--prompt-cache-size 10`

Per stored sequence, roughly:

- Linear / GDN state: ~48 layers × (fp32 recurrent `[48, 128, 128]` + small
  conv) ≈ **150 MB**, independent of context.
- Full-attention KV: 16 layers × 4 KV heads × 256 dim × 2 (K+V) × 2 bytes
  ≈ **64 KiB per token** (bf16).

At an 8k prompt that is ~0.15 + 0.50 ≈ **0.65 GiB per LRU entry**. Ten entries
plus the live working copy can be several GiB on top of 14.09 GiB weights
inside a 17.76 GiB recommended working set. Size 10 is mlx-lm’s default and
is what we run; it is **not** free. `--prompt-cache-bytes` is the actual
RAM cap if swap shows up. Do not raise size blindly.

---

## 2. `kv-bits` — server vs CLI

**Not on the server.** `server.py`’s argparse has no `--kv-bits`,
`--kv-group-size`, `--quantized-kv-start`, or `--max-kv-size`. The HTTP body
does not accept them either. `stream_generate` / `BatchGenerator` in the
server path never pass `kv_bits`.

Open requests: [ml-explore/mlx-lm#1043](https://github.com/ml-explore/mlx-lm/issues/1043),
[ml-explore/mlx-lm#1308](https://github.com/ml-explore/mlx-lm/issues/1308).

CLI that **does** quantize KV:

```bash
mlx_lm.generate --model … --kv-bits 4 --kv-group-size 64 --quantized-kv-start 5000
mlx_lm.cache_prompt --model … --kv-bits 4 --prompt-cache-file prefix.safetensors --prompt …
mlx_lm.generate --prompt-cache-file prefix.safetensors --prompt "…"
```

`maybe_quantize_kv_cache` only converts objects with `to_quantized()`
(`KVCache` → `QuantizedKVCache`). `ArraysCache` has no such method, so
**linear-attention state stays full precision** even on the CLI. On this
hybrid, kv-bits only shrinks the 16 FA layers (64 KiB/token → ~16 KiB/token
at 4-bit). Default `--quantized-kv-start 5000` leaves the first 5k tokens in
bf16, so inside Kiln’s 8k practical window the savings are small.

`mlx_lm.cache_prompt` writes a **file** for a later `generate` call. The HTTP
server never reads that file.

Do not add `--kv-bits` to `start-mlx.sh`. It is not a valid server flag.

---

## 3. `--draft-model` / speculative decoding on this 27B hybrid / 24 GB

### Server support in the abstract

The server **does** implement speculative decoding:

- CLI: `--draft-model PATH --num-draft-tokens N` (default N=3)
- HTTP: `"draft_model": "…", "num_draft_tokens": N`

Loading a draft sets `is_batchable = False`, so that request goes through
`_serve_single` → `stream_generate(..., draft_model=...)` →
`speculative_generate_step`.

### This checkpoint

`speculative_generate_step` **refuses** a non-trimmable cache before any token
is drafted:

```529:533:/opt/homebrew/lib/python3.14/site-packages/mlx_lm/generate.py
    if not cache.can_trim_prompt_cache(model_cache):
        types = {type(c).__name__ for c in model_cache if not c.is_trimmable()}
        raise ValueError(
            f"Speculative decoding requires a trimmable prompt cache " f"(got {types})."
        )
```

On Qwen3.5 that is `ValueError: Speculative decoding requires a trimmable
prompt cache (got {'ArraysCache'})`.

This is not theoretical. Same version, same cache type, HTTP path:
[ml-explore/mlx-lm#1446](https://github.com/ml-explore/mlx-lm/issues/1446)
(open on 0.31.3). `mlx_lm.generate --draft-model` hits the same raise.

The server will still **start**. `/v1/models` and `/health` succeed. The
failure is on the first completion. That is worse than a startup error.

### Draft model identity

Even if trim were implemented:

- Vocab must match. Server only **warns** on mismatch; `generate` **raises**.
  Qwen3 0.6B/1.7B (vocab 151 936) is the wrong family for this 248 320 vocab.
- Qwen3.6 MTP checkpoints (`model_type: qwen3_5_mtp`) are **not registered**
  in 0.31.3 ([#1462](https://github.com/ml-explore/mlx-lm/issues/1462)). This
  tree also **deletes** `mtp.*` weights when loading `qwen3_5`. There is no
  in-graph MTP drafter to turn on.
- A same-family tiny draft (e.g. Qwen3.5-0.8B 4/8-bit) is the only plausible
  pairing, and it still dies on `ArraysCache`.

### 24 GB M4 budget (why we would not turn it on even if it ran)

| | GiB |
|---|---|
| Weights (27B 4-bit) | 14.09 |
| Metal recommended working set | 17.76 |
| Headroom for activations + KV + LRU | ~3.7 |
| Tiny 0.8B 8-bit draft (order of magnitude) | ~1 |
| Two caches + speculative T>1 forwards | extra |

mlx-lm warns when model bytes exceed 90% of the recommended working set
(~15.9 GiB). The 27B alone is under that. 27B + draft + two caches is not a
comfortable fit on 24 GB; swap is likely. Speculative decoding also **disables
batching** (`is_batchable = False`).

**Feasible on this box, this model, this mlx-lm: no.** Do not pass
`--draft-model` to Kiln’s server.

---

## 4. Flags already in use

From `scripts/start-mlx.sh` / `docs/architecture.md`:

```
--decode-concurrency 1
--prompt-concurrency 1
--prefill-step-size 512
--prompt-cache-size 3
--prompt-cache-bytes 1G
--chat-template-args '{"enable_thinking":true,"reasoning_effort":"medium"}'
```

Keep them.

| Flag | Why it is right here |
|---|---|
| `--decode-concurrency 1` | One decode stream on 24 GB. Does not disable prefix cache. |
| `--prompt-concurrency 1` | One prefill at a time. Matches Kiln’s single in-flight generation. |
| `--prompt-cache-size 3` + `--prompt-cache-bytes 1G` | Hybrid LRU copies are large; 3/1G is what 24GB can hold. |
| `--chat-template-args` | Thinking on by default; changing this per request retokenizes the prefix and misses the LRU. |

Kiln also sends `stream_options.include_usage: true` and `model: "default_model"`.
Both are required for `cached_tokens` and to avoid a second weight load.

---

## What we may claim (HTTP / Kiln)

- Prefix **KV/state reuse across HTTP requests** via process-global
  `LRUPromptCache`, for **continuing** a conversation and for a **stable
  system** snapshot stored as a shorter prefix.
- `cached_tokens` is a real server field (`prompt_tokens_details`), visible
  on non-stream responses and on the final stream usage event when
  `include_usage` is set.
- Hybrid Qwen3.5 **does** hit the shorter-prefix path. Linear state is copied
  forward; FA KV is copied forward; no trim.
- `--decode-concurrency 1` is the correct 24 GB setting and does not turn the
  cache off.
- Sampling defaults (temp 1.0, top_p 0.95, top_k 20) come from this
  checkpoint’s `generation_config.json`.

## What only works on CLI (not Kiln’s HTTP path)

- `--kv-bits` / `--kv-group-size` / `--quantized-kv-start`
- `--prompt-cache-file` / `mlx_lm.cache_prompt`
- `--max-kv-size` (and it would not apply to this `make_cache()` anyway)
- `--draft-model` as a *working* speedup (the flag exists on the server too,
  but it errors on this architecture)

## What we must **not** claim

1. **Not** “speculative decoding is enabled / 1.5–2× decode on the 27B server.”
   The flag exists; this hybrid raises `ArraysCache` is not trimmable. Same
   on CLI. MTP drafters are unloaded / unregistered.
2. **Not** “the server is running `--kv-bits`” or “KV cache is 4-bit.” It is
   not wired. Even CLI kv-bits would only touch the 16 FA layers.
3. **Not** “every turn reuses 100% of the previous prompt+completion.” With
   `preserve_thinking: false`, thinking tokens are not in the next prompt, so
   `cached_tokens` is the common prefix, not the last completion.
4. **Not** “same system prompt + a new first user message always hits.” That
   needs a stored **shorter** system (or user) snapshot still in the LRU. A
   single longer “full conversation” entry cannot be trimmed on ArraysCache.
   Agentic “shared prefix, diverging suffix” is the documented weak case.
5. **Not** “Qwen3 0.6B/1.7B is a valid draft for this 27B.” Vocab 151 936 vs
   248 320.
6. **Not** “the 262 144 context window is usable on 24 GB.” Practical budget
   stays 8192. FA KV alone is ~64 KiB/token; activations and the LRU dominate
   long before the theoretical max.
7. **Not** “LM Studio / mlx-engine cache behavior is this server.” Different
   stack; several Qwen3.5 cache bugs were mlx-engine-only.
8. **Not** “keepalive `processed/total` is `cached_tokens`.” That is uncached
   prefill progress.
9. **Not** “`cache_prompt` files feed the HTTP LRU.” They do not.
10. **Not** “raising `--prompt-cache-size` is a free TTFT win.” Each hybrid
    snapshot is hundreds of MB at 8k; 10 copies can fight the 17.76 GiB
    working-set cap.

---

## Source map (0.31.3)

| Piece | Path |
|---|---|
| HTTP server, LRU construction, usage JSON, `--draft-model` | `mlx_lm/server.py` |
| `generate_step` / `speculative_generate_step` / `stream_generate` / CLI `kv-bits` + `draft-model` | `mlx_lm/generate.py` |
| File prompt cache + CLI `kv-bits` | `mlx_lm/cache_prompt.py` |
| `LRUPromptCache`, `ArraysCache`, `KVCache`, trim | `mlx_lm/models/cache.py` |
| Hybrid `make_cache` | `mlx_lm/models/qwen3_5.py` |
| Kiln launch flags | `kiln/scripts/start-mlx.sh` |
| Kiln `cached_tokens` client | `kiln/backend/app/providers/mlx.py` |
